FROM alpine:latest

# Install C++ compiler and build tools
RUN apk add --no-cache build-base

# Set working directory
WORKDIR /code

# Run as non-root user for security
RUN adduser -D runner
USER runner

# Default command
CMD ["g++"]
