# Use an official Python runtime as an image
FROM python:3.6

# The EXPOSE instruction indicates the ports on which a container 
# will listen for connections
# Since Flask apps listen to port 5000  by default, we expose it
EXPOSE 5000

# Sets the working directory for following COPY and CMD instructions
# Notice we haven’t created a directory by this name - this instruction 
# creates a directory with this name if it doesn’t exist
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt /app
RUN pip install -r requirements.txt

# Run app.py when the container launches
COPY app.py /app
COPY last_run.yaml /app
# RUN apt-get update \
#     && apt-get install -y cron \
#     && apt-get autoremove -y

# COPY parser.py /app
# RUN chmod +x /app/parser.py

# COPY ./parser /etc/cron.d/parser

# ADD start.sh /
# RUN chmod +x /start.sh
# RUN touch /var/log/task.log

CMD python app.py
