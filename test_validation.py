#!/usr/bin/env python3
"""Test BASE_URL validation"""

import os

# Test different BASE_URL values
test_cases = [
    ("https://docs.atlassian.com/test", "Invalid - wrong domain"),
    ("https://support.atlassian.com/", "Invalid - no endpoint"),
    ("https://support.atlassian.com/jira-service-management-cloud", "Valid"),
    ("https://support.atlassian.com/unknown-product", "Valid but unknown product"),
    ("http://support.atlassian.com/jira", "Invalid - not HTTPS"),
    ("support.atlassian.com/jira", "Invalid - no protocol"),
]

print("Testing BASE_URL validation...\n")

for url, expected in test_cases:
    print(f"Testing: {url}")
    print(f"Expected: {expected}")

    # Set the environment variable
    os.environ["BASE_URL"] = url

    # Import and run validation
    try:
        from scraper import validate_environment

        env_config = validate_environment()
        actual_url = env_config.get("BASE_URL")
        print(f"Result: {actual_url}")
    except Exception as e:
        print(f"Error: {e}")

    print("-" * 60)
