# Google Cloud staging infrastruktura

Terraform vytváří samostatnou VPC, privátní připojení ke Cloud SQL for PostgreSQL, VM s vyhrazeným service accountem, statickou veřejnou IP, perzistentní disk s denními snapshoty, Artifact Registry a dva prázdné Secret Manager secrety. Hodnoty tajemství záměrně nejsou Terraform proměnné, aby se neuložily do state.

## Předpoklady

- účet s oprávněním vytvářet uvedené GCP prostředky,
- `gcloud`, Terraform 1.6+ a Docker,
- billing zapnutý pro projekt,
- DNS zóna, ve které lze vytvořit A záznam,
- pro SSH přes IAP musí nasazující identita mít `roles/iap.tunnelResourceAccessor` a odpovídající OS Login roli.

Pro sdílené nebo produkční prostředí nejprve vytvořte samostatný, verzovaný GCS bucket pro Terraform state a zkopírujte `backend.tf.example` na `backend.tf`. Bucket samotný tento modul z důvodu bootstrapu nespravuje.

## 1. Infrastruktura

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# upravte projekt, region, zónu a doménu
terraform init
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
