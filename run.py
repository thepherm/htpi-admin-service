#!/usr/bin/env python
"""Simple runner script for Railway"""
from app.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())