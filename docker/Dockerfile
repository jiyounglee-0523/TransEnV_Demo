# Use the official PyTorch 2.0.1 image
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# Set the working directory
WORKDIR /workspace/TransEnV_Demo

# Install C extensions, git, etc.
RUN apt-get update && \
    apt-get remove -y nodejs libnode-dev libnode72 || true && \
    apt-get autoremove -y && \
    apt-get install -y --no-install-recommends \
    git \
    vim \
    build-essential \
    libpq-dev \
    curl \
    openssh-client \
    autossh \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# Install packages
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN rm requirements.txt