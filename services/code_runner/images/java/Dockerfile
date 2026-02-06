FROM eclipse-temurin:17-jdk-alpine


# Set working directory
WORKDIR /code

# Run as non-root user for security
RUN adduser -D runner
USER runner

# Default command
CMD ["java"]
