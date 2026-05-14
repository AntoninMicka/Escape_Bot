# AI Layer

Tahle vrstva drzi napojeni na lokální služby mimo herní state machine.

- `ollama_adapter.py` generuje textové reakce, analýzu hráčova popisu a bezpečné návrhy nápověd.
- `comfyui_adapter.py` posílá workflow do ComfyUI, typicky pro avatar/video reakce, stylizované snímky nebo lip-sync pipeline.

Adaptéry nemají samy měnit stav hry. Stav mění pouze backend po ověření přes ARG logiku.

