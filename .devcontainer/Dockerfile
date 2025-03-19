# Base image with Python
FROM mcr.microsoft.com/devcontainers/python:3.11

# Set up working directory
WORKDIR /workspace

USER root

RUN chown -R vscode:vscode /workspace

# Switch to vscode user before installation
USER vscode

# Copy dependencies for installation
COPY pyproject.toml poetry.lock ./

# Install Poetry globally for the vscode user
RUN curl -sSL https://install.python-poetry.org | python3 - 

# Ensure Poetry is in PATH
ENV PATH="/home/vscode/.local/bin:$PATH"

# Install Python dependencies using Poetry
RUN poetry install --no-root

# Set default shell
CMD [ "sleep", "infinity" ]
