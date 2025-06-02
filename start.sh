#!/bin/bash

rcc run -t producer -e devdata/env-for-producer.json

rcc run -t consumer -e devdata/env-for-consumer.json

