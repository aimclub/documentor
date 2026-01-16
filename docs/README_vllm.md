## vLLM: local server and integration

### Install and run
```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-VL-7B-Instruct \
  --dtype auto \
  --port 8000
```

### Environment variables
- `QWEN_BASE_URL=http://localhost:8000/v1`
- `QWEN_MODEL_NAME=Qwen2.5-VL-7B-Instruct`
- `QWEN_API_KEY=dummy`  # vLLM usually does not validate key

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
[Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5)

