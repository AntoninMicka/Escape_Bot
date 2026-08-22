# Google Cloud staging infrastruktura

Terraform vytváří samostatnou VPC, privátní připojení ke Cloud SQL for PostgreSQL, VM s vyhrazeným service accountem, statickou veřejnou IP, perzistentní disk s denními snapshoty, Artifact Registry a dva prázdné Secret Manager secrety. Hodnoty tajemství záměrně nejsou Terraform proměnné, aby se neuložily do state.

## Předpoklady

- účet s oprávněním vytvářet uvedené GCP prostředky,
- `gcloud`, Terraform 1.6+ a Docker,
- billing zapnutý pro projekt,
- DNS zóna, ve které lze vytvořit A záznam,
- pro SSH přes IAP musí nasazující identita mít `roles/iap.tunnelResourceAccessor` a odpovídající OS Login roli.

Terraform má deklarovaný GCS backend. Pro short-run vytvoří a zabezpečí verzovaný state bucket automaticky `bootstrap-state-bucket.sh`; jeho název je standardně `<project-id>-escape-bot-tfstate`. Bucket se záměrně nemaže společně s aplikační infrastrukturou, aby zůstal dostupný state, historie verzí a netajná konfigurace pro převzetí z jiného počítače.

## 1. Infrastruktura

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# upravte projekt, region, zónu a doménu
terraform init \
  -backend-config="bucket=PROJECT_ID-escape-bot-tfstate" \
  -backend-config="prefix=escape-bot/permanent"
terraform fmt -check
terraform validate
terraform plan -out=staging.tfplan
terraform apply staging.tfplan
```

Cloud SQL nemá veřejnou IPv4. Proxy na VM se připojuje přes privátní VPC a autentizuje service accountem VM bez staženého JSON klíče. VM má `cloud-platform` scope, ale skutečný přístup omezují IAM role Cloud SQL Client, Artifact Registry Reader, Secret Accessor pouze pro dva konkrétní secrety a Logs Writer.

## 2. Tajemství a databázový uživatel

Po prvním apply načtěte názvy z outputs a spusťte z kořene repozitáře:

```bash
./deploy/gcp/configure-secrets.sh \
  --project="$(terraform -chdir=infra/terraform output -raw project_id 2>/dev/null || echo PROJECT_ID)" \
  --instance="$(terraform -chdir=infra/terraform output -raw cloud_sql_instance)" \
  --admin-secret="$(terraform -chdir=infra/terraform output -raw admin_token_secret)" \
  --database-secret="$(terraform -chdir=infra/terraform output -raw database_password_secret)"
```

Pokud startup VM ukončil čekání před vytvořením verzí secretů, VM jednou restartujte. Nikdy nevkládejte hodnoty secretů do `terraform.tfvars`, image nebo repozitáře.

## 3. První release

Release lze sestavit pouze z čistého Git pracovního stromu:

```bash
IMAGE=$(./deploy/gcp/build-release.sh --project=PROJECT_ID --region=europe-west3 --version=v0.1.0)
```

Skript publikuje tag s Git SHA a volitelnou čitelnou verzí. Pro deploy použijte vypsaný digest:

```bash
./deploy/gcp/deploy.sh \
  --project=PROJECT_ID \
  --zone="$(terraform -chdir=infra/terraform output -raw vm_zone)" \
  --vm="$(terraform -chdir=infra/terraform output -raw vm_name)" \
  --image="$IMAGE"
```

Deploy přes IAP stáhne image, spustí dopředné schéma migrace, vymění aplikaci, čeká na `/api/ready` a při chybě automaticky vrátí předchozí image. Databázi automaticky nevrací. Explicitní aplikační rollback používá stejný příkaz přes `rollback.sh` s předchozím známým digestem.

## 4. DNS a ověření

Nastavte A záznam domény na output `public_ip`. Po propagaci DNS získá Caddy certifikát. Ověřte:

```bash
curl "https://$(terraform -chdir=infra/terraform output -raw domain)/api/health"
curl "https://$(terraform -chdir=infra/terraform output -raw domain)/api/ready"
```

Před produkčním použitím ověřte obnovu Cloud SQL PITR, obnovu snapshotu datového disku, restart VM, reconnect telefonů a celý sólo i týmový scénář.

## Krátkodobý profil pro akci

Soubor `short-run.tfvars.example` je oddělený od trvalého profilu. Používá `e2-medium`, menší disky a sedmidenní retenci snapshotů. Nastavením `enable_cloud_sql = false` nevytváří Cloud SQL, databázové heslo, privátní service networking ani Cloud SQL Auth Proxy. Jediná instance aplikace ukládá atomické JSON soubory na samostatný perzistentní disk. Tento režim není určen pro horizontální škálování; trvalý profil nadále používá PostgreSQL.

Prázdná proměnná `domain` aktivuje dočasnou adresu `<veřejná-IP-s-pomlčkami>.sslip.io`; registrace ani ruční DNS záznam nejsou potřeba. Pro dlouhodobý profil použijte vlastní doménu. Short-run operátor může ponechat prázdný i image digest: po prvním Terraform apply automaticky sestaví a publikuje image do právě vytvořeného Artifact Registry.

Celý cyklus lze řídit také druhou Qt aplikací `EscapeBotCloudOperator`, popsanou v `desktop/README.md`. Ekvivalentní provisioning z příkazové řádky provede inicializaci i výběr nebo vytvoření odděleného workspace:

```bash
./deploy/gcp/provision-short-run.sh \
  --terraform-dir=infra/terraform \
  --var-file=infra/terraform/short-run.tfvars \
  --workspace=event-2026 \
  --state-bucket=PROJECT_ID-escape-bot-tfstate
```

Pro 200 hráčů během pěti dnů odpovídá přibližně 40 hráčům denně. Při průměrně třech hráčích v týmu jde asi o 14 týmů denně. Výchozí limit čtyř současných týmů, dvouhodinová hra a patnáctiminutové odstupy poskytují za dvanáctihodinový den rezervu přibližně 24 týmových startů. Pokud by výrazně převládali sólo hráči, je nutné rezervace rozložit nebo upravit limit a ověřit zátěžovým testem.

Vytvoření používá vlastní vzdálený state/workspace oddělený od trvalého nasazení. Následující ruční varianta odpovídá lifecycle skriptu:

```bash
cp infra/terraform/short-run.tfvars.example infra/terraform/short-run.tfvars
./deploy/gcp/bootstrap-state-bucket.sh PROJECT_ID europe-west3 PROJECT_ID-escape-bot-tfstate
terraform -chdir=infra/terraform init -reconfigure \
  -backend-config="bucket=PROJECT_ID-escape-bot-tfstate" \
  -backend-config="prefix=escape-bot/short-run"
terraform -chdir=infra/terraform workspace new event-2026
terraform -chdir=infra/terraform plan -var-file=short-run.tfvars -out=short-run.tfplan
terraform -chdir=infra/terraform apply short-run.tfplan
```

### Doporučený cyklus

1. Nasadit ověřovací image a projít scénář.
2. Mezi testovacími obdobími prostředí pozastavit pomocí `pause-short-run.sh`; při pokračování použít `resume-short-run.sh`.
3. Po opravách nasadit nový image digest standardním `deploy.sh`.
4. Před ostrým startem spustit `event-lifecycle.sh --action=reset --label=pre-event`. Aplikace se zastaví, data se archivují, herní relace/lobby/leaderboard se vyčistí a nové starty zůstanou globálně vypnuté. Časová konfigurace zůstane zachována.
5. V adminu ověřit plán a ručně spustit herní provoz.
6. Po akci nejprve spustit `--action=archive --label=final`, potom archivy stáhnout.
7. Teprve po kontrole lokálního `archive-report.json` spustit destrukční cleanup.

Příklad resetu a závěrečné archivace:

```bash
./deploy/gcp/event-lifecycle.sh --project=PROJECT --zone=ZONE --vm=VM \
  --action=reset --label=pre-event

./deploy/gcp/event-lifecycle.sh --project=PROJECT --zone=ZONE --vm=VM \
  --action=archive --label=final

./deploy/gcp/collect-event-archives.sh PROJECT ZONE VM ./backups/event-2026
```

Po ověření staženého archivu:

```bash
./deploy/gcp/destroy-short-run.sh \
  --terraform-dir=infra/terraform \
  --var-file=infra/terraform/short-run.tfvars \
  --archive-dir=backups/event-2026 \
  --workspace=event-2026 \
  --state-bucket=PROJECT_ID-escape-bot-tfstate \
  --confirm-destroy=DESTROY-SHORT-RUN
```

Cleanup skript převede zadané cesty na absolutní, takže jej lze bezpečně spustit z kořene repozitáře podle příkladu výše.
