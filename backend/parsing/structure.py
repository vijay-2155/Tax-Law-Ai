"""Pydantic data models for the structured Income Tax Act hierarchy."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class Clause(BaseModel):
    identifier: str            # "a", "b", "i", "ii"
    text: str
    sub_clauses: list[Clause] = Field(default_factory=list)

    def full_text(self, indent: int = 0) -> str:
        prefix = "  " * indent
        lines = [f"{prefix}({self.identifier}) {self.text}"]
        for sc in self.sub_clauses:
            lines.append(sc.full_text(indent + 1))
        return "\n".join(lines)


class Subsection(BaseModel):
    number: str                # "1", "2", "2A"
    text: str
    clauses: list[Clause] = Field(default_factory=list)
    provisos: list[str] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)

    def full_text(self) -> str:
        parts = [f"({self.number}) {self.text}"]
        for clause in self.clauses:
            parts.append(clause.full_text(indent=1))
        for proviso in self.provisos:
            parts.append(f"  Provided that {proviso}")
        for explanation in self.explanations:
            parts.append(f"  Explanation: {explanation}")
        return "\n".join(parts)


class Section(BaseModel):
    number: str                # "80C", "392", "2"
    title: str                 # "Deduction in respect of..."
    act: Literal["1961", "2025"]
    chapter_number: str = ""   # "VIA", "XIX", "I"
    chapter_title: str = ""    # "Deductions to be made..."
    part: str | None = None    # "A", "B" for sub-parts
    full_text: str = ""        # Complete raw text of entire section
    subsections: list[Subsection] = Field(default_factory=list)
    income_head: str | None = None   # "Salaries", "House Property", etc.
    mapped_section: str | None = None  # Section number in the other Act
    page_start: int = 0
    page_end: int = 0

    @property
    def display_number(self) -> str:
        return f"Section {self.number}"

    @property
    def search_text(self) -> str:
        """Combined text for search/embedding."""
        return f"Section {self.number}: {self.title}\n\n{self.full_text}"


class Chapter(BaseModel):
    number: str               # "VIA", "XIX"
    title: str                # "Deductions to be made..."
    act: Literal["1961", "2025"]
    page_start: int = 0
    sections: list[Section] = Field(default_factory=list)


class ParsedAct(BaseModel):
    act_year: Literal["1961", "2025"]
    total_pages: int
    chapters: list[Chapter] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)  # Flat list for easy access

    def get_section(self, number: str) -> Section | None:
        return next((s for s in self.sections if s.number.upper() == number.upper()), None)

    def sections_by_head(self, head: str) -> list[Section]:
        return [s for s in self.sections if s.income_head == head]
