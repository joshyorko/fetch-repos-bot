#!/bin/zsh
# Script to remove finalizers from all roles, rolebindings, and serviceaccounts in the arc-runners namespace

set -e
NAMESPACE="arc-runners"

# Get all resource types
RESOURCES=(role rolebinding serviceaccount)

for TYPE in $RESOURCES; do
  for NAME in $(kubectl get $TYPE -n $NAMESPACE -o jsonpath='{.items[*].metadata.name}'); do
    echo "Processing $TYPE/$NAME..."
    kubectl get $TYPE $NAME -n $NAMESPACE -o json | \
      jq 'del(.metadata.finalizers)' | \
      kubectl replace -f -
  done
done

echo "All finalizers removed. You can now delete the namespace if needed."
