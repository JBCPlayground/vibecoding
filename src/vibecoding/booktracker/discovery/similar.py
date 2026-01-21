"""Similar books finder.

Finds books similar to a given book based on various criteria.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select, func, or_

from ..db.models import Book
from ..db.schemas import BookStatus
from ..db.sqlite import Database, get_db


@dataclass
class SimilarityScore:
    """Similarity score breakdown for a book match."""

    book: Book
    total_score: float = 0.0

    # Individual scores (0-1)
    author_score: float = 0.0
    genre_score: float = 0.0
    series_score: float = 0.0
    length_score: float = 0.0
    era_score: float = 0.0  # Publication year similarity
    rating_score: float = 0.0

    match_reasons: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate total score if not set."""
        if self.total_score == 0.0:
            self._calculate_total()

    def _calculate_total(self):
        """Calculate weighted total score."""
        weights = {
            "author": 0.30,
            "genre": 0.25,
            "series": 0.20,
            "length": 0.10,
            "era": 0.08,
            "rating": 0.07,
        }

        self.total_score = (
            self.author_score * weights["author"]
            + self.genre_score * weights["genre"]
            + self.series_score * weights["series"]
            + self.length_score * weights["length"]
            + self.era_score * weights["era"]
            + self.rating_score * weights["rating"]
        )


class SimilarBooksFinder:
    """Finds books similar to a given book."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize similar books finder.

        Args:
            db: Database instance
        """
        self.db = db or get_db()

    def find_similar(
        self,
        book_id: str,
        limit: int = 10,
        include_read: bool = False,
    ) -> list[SimilarityScore]:
        """Find books similar to the given book.

        Args:
            book_id: ID of the book to find similar books for
            limit: Maximum results
            include_read: Include already-read books in results

        Returns:
            List of books with similarity scores, sorted by score
        """
        with self.db.get_session() as session:
            # Get the source book
            source_book = session.get(Book, book_id)
            if not source_book:
                return []

            # Get candidate books
            stmt = select(Book).where(Book.id != book_id)

            if not include_read:
                stmt = stmt.where(
                    Book.status.in_([
                        BookStatus.WISHLIST.value,
                        BookStatus.ON_HOLD.value,
                    ])
                )

            candidates = list(session.execute(stmt).scalars().all())

            # Calculate similarity scores
            scored = []
            for candidate in candidates:
                score = self._calculate_similarity(source_book, candidate)
                if score.total_score > 0.1:  # Minimum threshold
                    session.expunge(candidate)
                    scored.append(score)

            # Sort by total score
            scored.sort(key=lambda s: s.total_score, reverse=True)

            return scored[:limit]

    def find_similar_to_favorites(
        self,
        min_rating: int = 4,
        limit: int = 10,
    ) -> list[SimilarityScore]:
        """Find books similar to highly-rated books.

        Args:
            min_rating: Minimum rating for favorite books
            limit: Maximum results

        Returns:
            List of books similar to favorites
        """
        with self.db.get_session() as session:
            # Get favorite books
            stmt = select(Book).where(
                Book.status == BookStatus.COMPLETED.value,
                Book.rating >= min_rating,
            )
            favorites = list(session.execute(stmt).scalars().all())

            if not favorites:
                return []

            # Get unread candidates
            stmt = select(Book).where(
                Book.status.in_([
                    BookStatus.WISHLIST.value,
                    BookStatus.ON_HOLD.value,
                ])
            )
            candidates = list(session.execute(stmt).scalars().all())

            # Calculate aggregate similarity to all favorites
            candidate_scores = {}
            for candidate in candidates:
                total_similarity = 0.0
                best_match_reasons = []

                for favorite in favorites:
                    score = self._calculate_similarity(favorite, candidate)
                    if score.total_score > total_similarity:
                        total_similarity = score.total_score
                        best_match_reasons = score.match_reasons

                if total_similarity > 0.1:
                    session.expunge(candidate)
                    candidate_scores[candidate.id] = SimilarityScore(
                        book=candidate,
                        total_score=total_similarity,
                        match_reasons=best_match_reasons,
                    )

            # Sort and return top results
            sorted_results = sorted(
                candidate_scores.values(),
                key=lambda s: s.total_score,
                reverse=True,
            )

            return sorted_results[:limit]

    def find_by_author(
        self,
        author: str,
        exclude_book_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[Book]:
        """Find other books by the same author.

        Args:
            author: Author name
            exclude_book_id: Book ID to exclude
            limit: Maximum results

        Returns:
            List of books by the author
        """
        with self.db.get_session() as session:
            stmt = select(Book).where(
                func.lower(Book.author).like(f"%{author.lower()}%")
            )

            if exclude_book_id:
                stmt = stmt.where(Book.id != exclude_book_id)

            stmt = stmt.order_by(Book.date_added.desc()).limit(limit)

            books = list(session.execute(stmt).scalars().all())
            for book in books:
                session.expunge(book)

            return books

    def find_in_same_series(
        self,
        series: str,
        exclude_book_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[Book]:
        """Find other books in the same series.

        Args:
            series: Series name
            exclude_book_id: Book ID to exclude
            limit: Maximum results

        Returns:
            List of books in the series, sorted by index
        """
        if not series:
            return []

        with self.db.get_session() as session:
            stmt = select(Book).where(
                func.lower(Book.series).like(f"%{series.lower()}%")
            )

            if exclude_book_id:
                stmt = stmt.where(Book.id != exclude_book_id)

            stmt = stmt.order_by(Book.series_index.asc().nullslast()).limit(limit)

            books = list(session.execute(stmt).scalars().all())
            for book in books:
                session.expunge(book)

            return books

    def find_by_tags(
        self,
        tags: list[str],
        match_all: bool = False,
        exclude_book_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[Book]:
        """Find books with matching tags.

        Args:
            tags: Tags to match
            match_all: If True, book must have all tags
            exclude_book_id: Book ID to exclude
            limit: Maximum results

        Returns:
            List of matching books
        """
        if not tags:
            return []

        with self.db.get_session() as session:
            stmt = select(Book)

            tag_conditions = []
            for tag in tags:
                tag_conditions.append(
                    func.lower(Book.tags).like(f'%"{tag.lower()}"%')
                )

            if match_all:
                for condition in tag_conditions:
                    stmt = stmt.where(condition)
            else:
                stmt = stmt.where(or_(*tag_conditions))

            if exclude_book_id:
                stmt = stmt.where(Book.id != exclude_book_id)

            stmt = stmt.order_by(Book.date_added.desc()).limit(limit)

            books = list(session.execute(stmt).scalars().all())
            for book in books:
                session.expunge(book)

            return books

    def _calculate_similarity(
        self,
        source: Book,
        candidate: Book,
    ) -> SimilarityScore:
        """Calculate similarity between two books.

        Args:
            source: Source book to compare against
            candidate: Candidate book

        Returns:
            SimilarityScore with breakdown
        """
        score = SimilarityScore(book=candidate)
        reasons = []

        # Author similarity
        if source.author and candidate.author:
            if source.author.lower() == candidate.author.lower():
                score.author_score = 1.0
                reasons.append(f"Same author: {source.author}")
            elif self._author_similarity(source.author, candidate.author) > 0.5:
                score.author_score = 0.5
                reasons.append(f"Similar author name")

        # Series similarity
        if source.series and candidate.series:
            if source.series.lower() == candidate.series.lower():
                score.series_score = 1.0
                reasons.append(f"Same series: {source.series}")

        # Genre/tag similarity
        source_tags = set(t.lower() for t in source.get_tags())
        candidate_tags = set(t.lower() for t in candidate.get_tags())

        if source_tags and candidate_tags:
            common_tags = source_tags & candidate_tags
            if common_tags:
                score.genre_score = len(common_tags) / max(
                    len(source_tags), len(candidate_tags)
                )
                if score.genre_score >= 0.5:
                    reasons.append(f"Shared genres: {', '.join(list(common_tags)[:3])}")

        # Length similarity
        if source.page_count and candidate.page_count:
            diff = abs(source.page_count - candidate.page_count)
            max_pages = max(source.page_count, candidate.page_count)
            score.length_score = max(0, 1 - (diff / max_pages))
            if score.length_score >= 0.8:
                reasons.append("Similar length")

        # Publication era similarity
        if source.publication_year and candidate.publication_year:
            year_diff = abs(source.publication_year - candidate.publication_year)
            score.era_score = max(0, 1 - (year_diff / 50))  # Within 50 years
            if score.era_score >= 0.9:
                reasons.append("Same publication era")

        # Rating similarity (if both rated)
        if source.rating and candidate.rating:
            rating_diff = abs(source.rating - candidate.rating)
            score.rating_score = 1 - (rating_diff / 4)  # Max diff is 4

        score.match_reasons = reasons
        score._calculate_total()

        return score

    def _author_similarity(self, author1: str, author2: str) -> float:
        """Calculate name similarity between authors.

        Uses simple word overlap for now.

        Args:
            author1: First author name
            author2: Second author name

        Returns:
            Similarity score 0-1
        """
        words1 = set(author1.lower().split())
        words2 = set(author2.lower().split())

        if not words1 or not words2:
            return 0.0

        common = words1 & words2
        total = words1 | words2

        return len(common) / len(total) if total else 0.0
