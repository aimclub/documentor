# Dockerfile for DotsOCR with vLLM
ARG VLLM_VERSION=v0.9.1
FROM vllm/vllm-openai:${VLLM_VERSION}

# Install required dependencies for DotsOCR
RUN pip install flash_attn==2.8.0.post2 --no-build-isolation
RUN pip install transformers==4.51.3

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False

# Create working directory for model
WORKDIR /workspace

# Copy and configure entrypoint script
COPY entrypoint-dotsocr.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
