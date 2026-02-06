FROM python:3.11-alpine

# Set working directory
WORKDIR /code

# Run as non-root user for security
RUN adduser -D runner
USER runner

# Default command
CMD ["python"]
