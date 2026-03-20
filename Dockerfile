FROM ubuntu:24.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

ENV CUDA_VISIBLE_DEVICES=""

# Update system and install basic packages
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y \
        openssh-server \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        git \
        vim \
        sudo \
        && rm -rf /var/lib/apt/lists/*

# Create SSH directory
RUN mkdir -p /var/run/sshd



# Set SSH to allow root login with password
RUN echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config
RUN echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config

# Set root password
RUN echo 'root:123456' | chpasswd

# Create application directory
WORKDIR /app

# Copy all term_agent files
COPY . /app/

RUN mkdir -p /app/hf_cache

# Create virtual environment
RUN python3 -m venv /app/.venv

# Activate virtual environment and install dependencies
RUN /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install --upgrade google-genai && \
    /app/.venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
    if [ -f /app/requirements.txt ]; then \
        /app/.venv/bin/pip install -r /app/requirements.txt; \
    fi

# Generate SSH keys
RUN ssh-keygen -A

# Generate SSH key pair for root
RUN mkdir -p /root/.ssh && ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N ""

# Copy entrypoint script and make it executable
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose SSH and API ports
EXPOSE 22 8000

# Set entrypoint script as entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
