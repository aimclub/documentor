## vLLM: local server and integration

### Install and run
```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model /path/to/dots-ocr-model \
  --dtype auto \
  --port 8000 \
  --trust-remote-code
```

### Environment variables
- `DOTS_OCR_BASE_URL=http://localhost:8000/v1`
- `DOTS_OCR_MODEL_NAME=/model`
- `DOTS_OCR_API_KEY=dummy`  # vLLM usually does not validate key

### Smoke test
```bash
curl http://localhost:8000/v1/models | jq
```

### Using with Documentor
OCR config will read the variables from `.env` via `documentor/core/load_env.py` automatically.

### Docker & Compose

- **Dockerfile**: [Dockerfile.dotsocr](Dockerfile.dotsocr)
- **Docker Compose**: [compose.yml](compose.yml)

### Entrypoint script

- **Entrypoint script**: [entrypoint.sh](entrypoint.sh)

### Models installation

You can install models from Hugging Face.

[DotsOCR](https://huggingface.co/rednote-hilab/dots.ocr)

