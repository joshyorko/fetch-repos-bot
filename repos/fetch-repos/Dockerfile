# Base on the official GitHub Actions Runner image
FROM ghcr.io/actions/actions-runner:latest
# Switch to root for installations
USER root

# Install rcc (Robocorp Command Center)
RUN curl -o rcc https://github.com/joshyorko/rcc/releases/download/v18.13.1/rcc-linux64 \
 && chmod a+x rcc \
 && mv rcc /usr/local/bin/

# Copy configuration and values for fetch-repos
# These files are copied to repos/ by the GitHub Action before building
COPY conda.yaml /workspace/conda.yaml
COPY robot.yaml /workspace/robot.yaml

WORKDIR /workspace

# Switch to runner user and set up holotree environment
USER runner
RUN rcc config identity -t
RUN rcc holotree vars

# The holotree environment is now created and available in the runner's home directory
