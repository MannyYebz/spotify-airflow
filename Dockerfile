FROM apache/airflow:2.11.2-python3.12
WORKDIR /opt/airflow
COPY --chown=airflow:root pyproject.toml README.md requirements-airflow.txt ./
COPY --chown=airflow:root src/ ./src/
RUN mkdir -p /opt/airflow/tokens
RUN pip install --no-cache-dir -r requirements-airflow.txt
COPY --chown=airflow:root dags/ ./dags/
COPY --chown=airflow:root scripts/init_airflow.py ./scripts/init_airflow.py
