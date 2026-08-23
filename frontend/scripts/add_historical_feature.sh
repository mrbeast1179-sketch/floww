#!/bin/bash
# Script to apply historical data feature to FlowseekerPro

# Add yesterday option to dropdown
sed -i '' 's/<option value="today">Today<\/option><option value="1h">/ <option value="today">Today<\/option>\n        <option value="yesterday">Yesterday<\/option>\n        <option value="1h">/' frontend/src/components/flowseeker/FlowseekerPro.jsx

echo "Partial changes applied - manual review needed"