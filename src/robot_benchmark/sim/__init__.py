"""An abstract supervision environment: a latent task process, parametric VLAs, and a text perception model.

It reproduces the real harness's decision interface (run_policy with an optional prompt, complete; any prompt restarts)
so the same agents and baselines run on it, with no images, GPU or real policy. Design: docs/env_design.md. Results are
`sim_development` records and are never mixed with benchmark scores."""
