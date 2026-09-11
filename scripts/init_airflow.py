"""Idempotent local Compose initialization; admin secrets never appear in argv."""

import os
import subprocess

from airflow.www.app import create_app


def main() -> None:
    subprocess.run(["airflow", "db", "migrate"], check=True)
    app = create_app()
    with app.app_context():
        security = app.appbuilder.sm
        username = os.environ["AIRFLOW_ADMIN_USER"]
        if not security.find_user(username=username):
            user = security.add_user(
                username=username,
                first_name="Airflow",
                last_name="Admin",
                email=os.environ["AIRFLOW_ADMIN_EMAIL"],
                role=security.find_role("Admin"),
                password=os.environ["AIRFLOW_ADMIN_PASSWORD"],
            )
            if not user:
                raise RuntimeError("Could not create Airflow admin")


if __name__ == "__main__":
    main()
