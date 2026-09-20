# Running inside a company

Every setting in this project's CI, and in the workflows `registry init` writes, is a GitHub Actions
variable whose default reproduces the public github.com run. A copy on a company GitHub Enterprise
Server instance configures itself from its settings page and never edits a workflow.

[Rolling out AART on GitHub Enterprise Server](github-enterprise-rollout.md) walks it in
order — put `aart-cli` on the instance, configure its CI, create a registry, configure the
registry's CI, point people at it — and lists every variable.
