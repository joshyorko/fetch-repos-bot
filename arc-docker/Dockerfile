# Base on the official GitHub Actions Runner image
FROM ghcr.io/actions/actions-runner:2.324.0

# Switch to root for installations
USER root

# Install Node.js with minimal extras
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
 && apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# Install Playwright and delegate OS deps + browsers
RUN npm install -g playwright \
 && npx playwright install-deps \
 && npx playwright install --with-deps

# Install rcc (Robocorp Command Center)
RUN curl -o rcc https://cdn.sema4.ai/rcc/releases/latest/linux64/rcc \
 && chmod a+x rcc \
 && mv rcc /usr/local/bin/

# Copy configuration and values for fetch-repos
COPY conda.yaml /workspace/conda.yaml
COPY robot.yaml /workspace/robot.yaml

WORKDIR /workspace

# Switch to runner user and set up holotree environment
USER runner
RUN rcc config identity -t
RUN rcc holotree vars

# The holotree environment is now created and available in the runner's home directory
