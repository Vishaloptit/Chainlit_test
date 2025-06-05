#!/bin/bash
# Variables (adjust these for your environment)
CONTAINER_ID="postgres"   # Use the postgres container name as defined in your docker-compose
POSTGRES_USER="root"      # From your docker-compose (defaults to "root")
DATABASE="postgres"       # From your docker-compose (defaults to "postgres")
OUTPUT_FILE="/home/optit/SupportTicketSystem-AI/Chainlit/logs/queries_each_day.csv"
TEMP_QUERY_FILE="/tmp/query.sql"

# Write the SQL query to a local temporary file using a heredoc.
cat <<'EOF' > query.sql
COPY (
  SELECT 
    DATE("createdAt") AS query_date,
    "name" AS user_email,
    COUNT(*) AS total_queries_by_user
  FROM "Step"
  WHERE type = 'user_message'
  GROUP BY DATE("createdAt"), "name"
  ORDER BY query_date, user_email
) TO STDOUT WITH CSV HEADER;
EOF

# Copy the query file into the Postgres container
docker cp query.sql "$CONTAINER_ID":/tmp/query.sql

# Check if the output file exists (in the mounted location)
if docker exec "$CONTAINER_ID" test -f "$OUTPUT_FILE"; then
    echo "Appending new data to existing file..."
    docker exec "$CONTAINER_ID" bash -c "psql -U $POSTGRES_USER -d $DATABASE -f /tmp/query.sql" >> "$OUTPUT_FILE"
else
    echo "Creating new file with header..."
    docker exec "$CONTAINER_ID" bash -c "psql -U $POSTGRES_USER -d $DATABASE -f /tmp/query.sql" > "$OUTPUT_FILE"
fi

# Clean up the temporary query file from the host
rm query.sql
