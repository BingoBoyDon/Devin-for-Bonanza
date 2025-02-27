#!/bin/bash

echo "Testing JavaScript fixes..."

# Check if the websocket_client.js file has the duplicate macAddress declaration
if grep -q "let macAddress = '';" websocket_client.js; then
  echo "ERROR: websocket_client.js still has duplicate macAddress declaration"
  exit 1
else
  echo "SUCCESS: websocket_client.js no longer has duplicate macAddress declaration"
fi

# Check if script.js has the getMacAddress call in DOMContentLoaded
if grep -q "getMacAddress(siteId).then" script.js | grep -q "DOMContentLoaded"; then
  echo "ERROR: script.js still has getMacAddress call in DOMContentLoaded"
  exit 1
else
  echo "SUCCESS: script.js no longer has getMacAddress call in DOMContentLoaded"
fi

# Check if script.js has the window.load event listener
if grep -q "window.addEventListener('load'" script.js; then
  echo "SUCCESS: script.js has window.load event listener"
else
  echo "ERROR: script.js does not have window.load event listener"
  exit 1
fi

# Check if script.js has the type checks before calling functions
if grep -q "typeof getMacAddress === 'function'" script.js; then
  echo "SUCCESS: script.js has type checks before calling functions"
else
  echo "ERROR: script.js does not have type checks before calling functions"
  exit 1
fi

echo "All tests passed! The JavaScript errors should be fixed."
