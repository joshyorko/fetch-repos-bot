#!/usr/bin/env bash
set -e

# Usage: ./install.sh <repo-dir> [build|--dry-run]
REPO_DIR=${1:?'Usage: $0 <repo-dir> [build|--dry-run]'}
BUILD_FLAG=${2:-}
DRY_RUN=false
if [ "$BUILD_FLAG" == "--dry-run" ]; then
    DRY_RUN=true
fi

VALUES_FILE="repos/$REPO_DIR/values.yaml"
DOCKERFILE="repos/$REPO_DIR/Dockerfile"

YQ_COMMAND=""

# Function to detect yq type and install if needed
detect_yq_type() {
    if command -v yq &> /dev/null; then
        # Check if it's the Go-based yq (mikefarah/yq) by testing a unique Go-yq feature
        if echo 'test: value' | yq e '.test' - &> /dev/null; then
            echo "go"
        # Check if it's the Python-based yq by testing jq-style syntax
        elif echo '{"test": "value"}' | yq -r .test &> /dev/null 2>&1; then
            echo "python"
        else
            echo "unknown"
        fi
    else
        echo "none"
    fi
}

# Function to find or install yq
setup_yq() {
    YQ_TYPE=$(detect_yq_type)
    
    case $YQ_TYPE in
        "go")
            YQ_COMMAND="yq"
            echo "Go-based yq (mikefarah/yq) found in PATH."
            return 0
            ;;
        "python")
            echo "Python-based yq found, but we need Go-based yq for this script."
            echo "Installing Go-based yq alongside existing Python yq..."
            install_go_yq
            return $?
            ;;
        "unknown")
            echo "Unknown yq version found. Installing Go-based yq..."
            install_go_yq
            return $?
            ;;
        "none")
            echo "No yq found. Installing both Python-based and Go-based yq..."
            install_python_yq
            install_go_yq
            return $?
            ;;
    esac
}

# Function to install Python-based yq
install_python_yq() {
    echo "Installing Python-based yq..."
    if command -v pip3 &> /dev/null; then
        pip3 install --user yq
    elif command -v pip &> /dev/null; then
        pip install --user yq
    else
        echo "Warning: pip not found, skipping Python yq installation"
        return 1
    fi
}

# Function to install Go-based yq (mikefarah/yq)
install_go_yq() {
    # Download official binary to /usr/local/bin
    echo "Downloading Go-based yq (mikefarah/yq) binary to /usr/local/bin/yq-go..."
    if sudo curl -fsSL "https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64" -o "/usr/local/bin/yq-go"; then
        sudo chmod +x "/usr/local/bin/yq-go"
        # Verify the downloaded binary
        if /usr/local/bin/yq-go --version &> /dev/null; then
            YQ_COMMAND="/usr/local/bin/yq-go"
            echo "Go-based yq downloaded and installed successfully to /usr/local/bin/yq-go."
            return 0
        else
            echo "Downloaded yq binary but it's not executable or failed verification."
        fi
    else
        echo "Failed to download Go-based yq binary."
    fi

    echo "Error: Go-based yq could not be installed. Please install yq manually."
    exit 1
}

# Call setup_yq early
setup_yq

if [ ! -f "$VALUES_FILE" ]; then
  echo "Values file not found: $VALUES_FILE"
  exit 1
fi

if [[ "$BUILD_FLAG" == "build" ]]; then
  echo "Building and pushing image for $REPO_DIR"
  GITHUB_URL=$(${YQ_COMMAND} e '.githubConfigUrl' "$VALUES_FILE")
  OWNER_REPO=${GITHUB_URL#https://github.com/}
  ORG=${OWNER_REPO%/*}
  REPO_NAME=${OWNER_REPO##*/}
  IMAGE="ghcr.io/${ORG}/${REPO_NAME}-runner:latest"
  if [ -f "$DOCKERFILE" ]; then
    docker build -t "$IMAGE" "repos/$REPO_DIR"
    docker push "$IMAGE"
  else
    echo "No Dockerfile found in repos/$REPO_DIR, skipping build."
  fi
fi

# Install ARC controller (unless dry-run)
if [ "$DRY_RUN" != "true" ]; then
    NAMESPACE="arc-systems"
    helm upgrade --install arc \
      --namespace "$NAMESPACE" --create-namespace \
      oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller \
      --wait
fi

# Ensure runner namespace and GHCR secret

# Prefer pre-defined-secret.yaml for the private key, otherwise fall back to .private-key.pem
SECRET_FILE="pre-defined-secret.yaml"
PEM_FILE=$(ls -1t *.private-key.pem 2>/dev/null | head -n 1)
PRIVATE_KEY_CONTENT=""

if [[ -f "$SECRET_FILE" ]]; then
  # Extract github_app_private_key from the YAML file
  PRIVATE_KEY_CONTENT=$(awk '/github_app_private_key:/{print substr($0, index($0,$2))}' "$SECRET_FILE")
  if [[ -z "$PRIVATE_KEY_CONTENT" ]]; then
    echo "Error: pre-defined-secret.yaml found but github_app_private_key is empty."
    exit 1
  fi
elif [[ -f "$PEM_FILE" ]]; then
  PRIVATE_KEY_CONTENT="$(cat "$PEM_FILE")"
else
  echo "Error: Neither pre-defined-secret.yaml nor .private-key.pem file found in the current directory."
  exit 1
fi

if [ "$DRY_RUN" == "true" ]; then
    # For dry-run, create the secret YAML file first, then apply it
    echo "Creating secret YAML for dry-run..."
    kubectl create secret generic pre-defined-secret \
      --namespace=arc-runners  \
      --from-literal=github_app_id=1354710 \
      --from-literal=github_app_installation_id=69321446 \
      --from-literal=github_app_private_key="$(cat "$PEM_FILE")" \
      --dry-run=client -o yaml > pre-defined-secret.yaml
    echo "Secret YAML saved to pre-defined-secret.yaml"
    
    # Apply the secret (needed for the runner scale set dry-run to work)
    kubectl create namespace arc-runners || true
    kubectl apply -f pre-defined-secret.yaml
else
    kubectl create namespace arc-runners || true
    kubectl create secret generic pre-defined-secret \
      --namespace=arc-runners  \
      --from-literal=github_app_id=1354710 \
      --from-literal=github_app_installation_id=69321446 \
      --from-literal=github_app_private_key="$(cat "$PEM_FILE")" || true
fi

# Install runner scale set for the specified repo
RANGE_NAME=$(${YQ_COMMAND} e '.runnerScaleSetName' "$VALUES_FILE")
if [ "$DRY_RUN" == "true" ]; then
    echo "---"
    echo "Performing a dry run of the runner scale set."
    echo "This will output the Kubernetes YAML. The following error is expected during a dry-run"
    echo "because the controller is not actually running."
    echo "---"
    helm upgrade --install "$RANGE_NAME" \
      --namespace arc-runners --create-namespace \
      -f "$VALUES_FILE" \
      oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \
      --dry-run
    echo "---"
    echo "Dry run complete."
    echo "---"
else
    helm upgrade --install "$RANGE_NAME" \
      --namespace arc-runners --create-namespace \
      -f "$VALUES_FILE" \
      oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
fi