"""Contract management for agent initialization.

Contracts track what each agent needs from its dependencies (inputs)
and what it provides to its dependents (outputs). They are stored in
.poag/ directories within each flake and tracked in git.
"""

import json
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from poag_sf.logging import stderr


class ContractIndex(BaseModel):
    """Index tracking contract status for a flake.

    Stored in .poag/index.json for each flake.
    """
    last_commit: str = Field(description="Git commit hash when contracts were last generated")
    contracts: dict[str, list[str]] = Field(
        default_factory=lambda: {"inputs": [], "outputs": []},
        description="Lists of contract files that exist"
    )


class ContractManager:
    """Manages contract files for agent initialization."""

    def __init__(self, flake_path: Path):
        """Initialize contract manager for a specific flake.

        Args:
            flake_path: Path to the flake directory
        """
        self.flake_path = flake_path
        self.poag_dir = flake_path / ".poag"
        self.contracts_dir = self.poag_dir / "contracts"
        self.inputs_dir = self.contracts_dir / "inputs"
        self.outputs_dir = self.contracts_dir / "outputs"
        self.index_path = self.poag_dir / "index.json"

    def ensure_directories(self) -> None:
        """Create .poag directory structure if it doesn't exist."""
        self.poag_dir.mkdir(exist_ok=True)
        self.contracts_dir.mkdir(exist_ok=True)
        self.inputs_dir.mkdir(exist_ok=True)
        self.outputs_dir.mkdir(exist_ok=True)

    def get_current_commit(self) -> Optional[str]:
        """Get current git commit hash for this flake.

        Returns:
            Commit hash or None if not in a git repo
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.flake_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def load_index(self) -> Optional[ContractIndex]:
        """Load the contract index from .poag/index.json.

        Returns:
            ContractIndex if exists, None otherwise
        """
        if not self.index_path.exists():
            return None

        try:
            with open(self.index_path, "r") as f:
                data = json.load(f)

            stderr.print(f"[dim]      📄 Read {self.index_path.relative_to(self.flake_path.parent)}[/dim]")
            return ContractIndex(**data)
        except Exception as e:
            stderr.print(f"[yellow]      ⚠ Failed to load index: {e}[/yellow]")
            return None

    def save_index(self, index: ContractIndex) -> None:
        """Save contract index to .poag/index.json.

        Args:
            index: ContractIndex to save
        """
        self.ensure_directories()

        with open(self.index_path, "w") as f:
            json.dump(index.model_dump(), f, indent=2)

        rel_path = self.index_path.relative_to(self.flake_path.parent)
        stderr.print(f"[green]      ✓ Wrote {rel_path}[/green]")

    def are_contracts_current(self) -> bool:
        """Check if contracts exist and are up to date with current git commit.

        Returns:
            True if contracts are current, False if they need regeneration
        """
        index = self.load_index()
        if not index:
            stderr.print(f"[dim]      No index found, contracts need generation[/dim]")
            return False

        current_commit = self.get_current_commit()
        if not current_commit:
            stderr.print(f"[yellow]      ⚠ Not in git repo, cannot verify contract freshness[/yellow]")
            return False

        if index.last_commit != current_commit:
            stderr.print(f"[dim]      Contracts stale (commit {index.last_commit[:7]} → {current_commit[:7]})[/dim]")
            return False

        # Verify contract files actually exist
        for contract_file in index.contracts.get("inputs", []):
            if not (self.inputs_dir / contract_file).exists():
                stderr.print(f"[yellow]      ⚠ Missing input contract: {contract_file}[/yellow]")
                return False

        for contract_file in index.contracts.get("outputs", []):
            if not (self.outputs_dir / contract_file).exists():
                stderr.print(f"[yellow]      ⚠ Missing output contract: {contract_file}[/yellow]")
                return False

        stderr.print(f"[dim]      ✓ Contracts current (commit {current_commit[:7]})[/dim]")
        return True

    def write_input_contract(self, dependency_name: str, content: str) -> None:
        """Write a contract describing what we need from a dependency.

        Args:
            dependency_name: Name of the dependency flake
            content: Contract content (markdown)
        """
        self.ensure_directories()

        contract_path = self.inputs_dir / f"{dependency_name}.md"
        with open(contract_path, "w") as f:
            f.write(content)

        rel_path = contract_path.relative_to(self.flake_path.parent)
        stderr.print(f"[green]      ✓ Wrote {rel_path}[/green]")

    def write_output_contract(self, dependent_name: str, content: str) -> None:
        """Write a contract describing what we provide to a dependent.

        Args:
            dependent_name: Name of the dependent flake
            content: Contract content (markdown)
        """
        self.ensure_directories()

        contract_path = self.outputs_dir / f"{dependent_name}.md"
        with open(contract_path, "w") as f:
            f.write(content)

        rel_path = contract_path.relative_to(self.flake_path.parent)
        stderr.print(f"[green]      ✓ Wrote {rel_path}[/green]")

    def read_input_contract(self, dependency_name: str) -> Optional[str]:
        """Read a contract describing what we need from a dependency.

        Args:
            dependency_name: Name of the dependency flake

        Returns:
            Contract content or None if doesn't exist
        """
        contract_path = self.inputs_dir / f"{dependency_name}.md"
        if not contract_path.exists():
            return None

        rel_path = contract_path.relative_to(self.flake_path.parent)
        stderr.print(f"[dim]      📄 Read {rel_path}[/dim]")

        return contract_path.read_text()

    def read_output_contract(self, dependent_name: str) -> Optional[str]:
        """Read a contract describing what we provide to a dependent.

        Args:
            dependent_name: Name of the dependent flake

        Returns:
            Contract content or None if doesn't exist
        """
        contract_path = self.outputs_dir / f"{dependent_name}.md"
        if not contract_path.exists():
            return None

        rel_path = contract_path.relative_to(self.flake_path.parent)
        stderr.print(f"[dim]      📄 Read {rel_path}[/dim]")

        return contract_path.read_text()

    def get_all_contracts(self) -> dict[str, dict[str, str]]:
        """Get all contracts for this flake.

        Returns:
            Dict with 'inputs' and 'outputs' keys, each mapping dependency name to contract content
        """
        contracts = {"inputs": {}, "outputs": {}}

        if self.inputs_dir.exists():
            for contract_file in self.inputs_dir.glob("*.md"):
                dep_name = contract_file.stem
                contracts["inputs"][dep_name] = contract_file.read_text()

        if self.outputs_dir.exists():
            for contract_file in self.outputs_dir.glob("*.md"):
                dep_name = contract_file.stem
                contracts["outputs"][dep_name] = contract_file.read_text()

        return contracts

    def update_index_after_generation(self, input_contracts: list[str], output_contracts: list[str]) -> None:
        """Update index.json after contract generation.

        Args:
            input_contracts: List of dependency names for which input contracts were created
            output_contracts: List of dependent names for which output contracts were created
        """
        current_commit = self.get_current_commit()
        if not current_commit:
            stderr.print(f"[yellow]      ⚠ Not in git repo, cannot track commit in index[/yellow]")
            current_commit = "unknown"

        index = ContractIndex(
            last_commit=current_commit,
            contracts={
                "inputs": [f"{dep}.md" for dep in input_contracts],
                "outputs": [f"{dep}.md" for dep in output_contracts],
            }
        )

        self.save_index(index)
