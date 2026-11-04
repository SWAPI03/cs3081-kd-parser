# Image for the teacher-labelling workers (Task 1). Small: Python + boto3 only.
# Build from the repository root:  docker build -f worker/Dockerfile -t kd-worker:v1 .
FROM python:3.11.10-slim
WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker/s3util.py worker/teacher.py worker/label.py ./worker/
COPY prompts/teacher_prompt.txt ./prompts/teacher_prompt.txt
ENV PYTHONUNBUFFERED=1 PROMPT_FILE=/app/prompts/teacher_prompt.txt
ENTRYPOINT ["python", "worker/label.py"]
