# Offline tiny-controller pilot

Run against an already loaded endpoint:

```powershell
.app-venv/Scripts/python.exe experimental/benchmark/evaluate-micro-controller.py --base-url http://127.0.0.1:8091/v1 --model micro-controller --output experimental/results/new-controller-result.json
```

The old `benchmarks/evaluate-micro-controller.py` command remains a compatibility
entry point. The evaluator does not install, start or switch models. `--limit`
samples cannot pass the full pilot gate. The 42 fixtures are engineer-authored,
not independent held-out evidence; training on them invalidates a held-out claim.
