#!/bin/bash
cd /app && uvicorn inventory_demo.app.main:app --host 0.0.0.0 --port 8080
