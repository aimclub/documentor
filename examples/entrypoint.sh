#!/bin/bash
set -ex
echo "--- Starting DotsOCR setup and server ---"

# Create symlink for DotsOCR model
ln -sf /model /workspace/DotsOCR
export PYTHONPATH=/workspace:$PYTHONPATH

# Test model access
echo "Testing model access..."
python3 -c "import sys; sys.path.insert(0, '/workspace'); from DotsOCR import modeling_dots_ocr_vllm; print('Import successful')" || echo "Import failed"

# Start vLLM server
echo "Starting vLLM server..."
exec vllm serve /model \
    --api-key="${API_KEY:-your-api-key-here}" \
    --tensor-parallel-size="${TENSOR_PARALLEL_SIZE:-1}" \
    --gpu-memory-utilization="${GPU_MEMORY_UTILIZATION:-0.8}" \
    --max-model-len="${MAX_MODEL_LEN:-4096}" \
    --enforce-eager \
    --served-model-name="${SERVED_MODEL_NAME:-DotsOCR}" \
    --trust-remote-code
