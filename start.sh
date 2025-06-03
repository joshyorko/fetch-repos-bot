#!/bin/bash

rcc run -t producer -e devdata/env-for-producer.json
python3 scripts/generate_shards_and_matrix.py 3
rcc run -t consumer -e devdata/env-for-consumer.json

