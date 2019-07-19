FROM python:3.5-slim

#RUN apt-get update
#RUN apt-get install -y --no-install-recommends build-essential;

# Set environment variables 

# Don't create .pyc files (why don't we want these?)
ENV PYTHONDONTWRITEBYTECODE 1  
# Prevent docker from buffering console output
ENV PYTHONUNBUFFERED 1

# Set working directory for subsequent RUN ADD COPY CMD instructions
RUN mkdir /app
WORKDIR /app

# copy the entire project into the app directory.
# should we just copy over the code in src/ and requirements.txt?
COPY . /app/

# Install our dependancies (currently installing on the base image, not in venv)
RUN pip install -r requirements.txt

# RUN adduser --disabled-password appuser
# USER appuser

# The port
EXPOSE 8000

# Command to run when the container is started
# now uses docker-compose.yml
#CMD ["python", "src/manage.py", "runserver", "0.0.0.0:8000"]




