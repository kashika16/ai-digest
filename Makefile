PYTHON ?= python3

.PHONY: test preview preview-html send send-force

test:
	$(PYTHON) -m unittest discover -s tests

preview:
	$(PYTHON) run_digest.py --preview --ignore-seen

preview-html:
	$(PYTHON) run_digest.py --preview-html ./logs/email-preview.html --ignore-seen

send:
	$(PYTHON) run_digest.py

send-force:
	$(PYTHON) run_digest.py --ignore-seen
