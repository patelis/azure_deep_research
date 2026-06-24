"""Azure-native deep research backend.

Public surface used in-process by the py-shiny frontend:

- ``clarifier.clarify``        — clarify the request / propose a plan (Responses API).
- ``pipeline.run_research``    — execute an approved plan end-to-end and return the report.
- ``email.send_report_email``  — email a markdown report via Azure Communication Services.
- ``keystore`` (validate/consume) — per-user access keys + daily run cap.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
