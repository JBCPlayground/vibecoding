"""Manager for reading lists and recommendations."""

from collections import Counter
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import func, asc, desc
from sqlalchemy.orm import Session

from ..db.sqlite import Database
from ..db.models import Book
from ..db.schemas import BookStatus
from .models import ReadingList, ReadingListBook
from .schemas import (
    ReadingListCreate,
    ReadingListUpdate,
    ReadingListResponse,
    ReadingListSummary,
    ListBookCreate,
    ListBookResponse,
    ListBookWithDetails,
    ReadingListWithBooks,
    ListType,
    AutoListType,
    BookRecommendation,
    RecommendationReason,
    RecommendationSet,
    SimilarBook,
    GenreRecommendations,
    AuthorRecommendations,
    RecommendationStats,
)


class ReadingListManager:
    """Manager for reading lists operations."""

    def __init__(self, db: Database):
        """Initialize the reading list manager.

        Args:
            db: Database instance
        """
        self.db = db

    # ========================================================================
    # Reading List CRUD
    # ========================================================================

    def create_list(self, reading_list: ReadingListCreate) -> ReadingListResponse:
        """Create a new reading list.

        Args:
            reading_list: List data to create

        Returns:
            Created list response
        """
        with self.db.get_session() as session:
            db_list = ReadingList(
                name=reading_list.name,
                description=reading_list.description,
                list_type=reading_list.list_type.value,
                is_public=reading_list.is_public,
                is_pinned=reading_list.is_pinned,
                color=reading_list.color,
                icon=reading_list.icon,
            )

            session.add(db_list)
            session.flush()

            return self._to_list_response(db_list)

    def get_list(self, list_id: UUID) -> Optional[ReadingListResponse]:
        """Get a reading list by ID.

        Args:
            list_id: List UUID

        Returns:
            List response or None if not found
        """
        with self.db.get_session() as session:
            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            if not reading_list:
                return None

            return self._to_list_response(reading_list)

    def update_list(
        self, list_id: UUID, updates: ReadingListUpdate
    ) -> Optional[ReadingListResponse]:
        """Update a reading list.

        Args:
            list_id: List UUID
            updates: Fields to update

        Returns:
            Updated list response or None if not found
        """
        with self.db.get_session() as session:
            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            if not reading_list:
                return None

            update_data = updates.model_dump(exclude_unset=True)

            for field, value in update_data.items():
                if field == "list_type" and value is not None:
                    setattr(reading_list, field, value.value if hasattr(value, 'value') else value)
                else:
                    setattr(reading_list, field, value)

            session.flush()

            return self._to_list_response(reading_list)

    def delete_list(self, list_id: UUID) -> bool:
        """Delete a reading list.

        Args:
            list_id: List UUID

        Returns:
            True if deleted, False if not found
        """
        with self.db.get_session() as session:
            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            if not reading_list:
                return False

            # Delete all list book entries
            session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id)
            ).delete()

            session.delete(reading_list)
            return True

    def get_all_lists(
        self,
        list_type: Optional[ListType] = None,
        pinned_only: bool = False,
        limit: int = 50,
    ) -> list[ReadingListSummary]:
        """Get all reading lists.

        Args:
            list_type: Filter by list type
            pinned_only: Only show pinned lists
            limit: Max lists to return

        Returns:
            List of list summaries
        """
        with self.db.get_session() as session:
            query = session.query(ReadingList)

            if list_type is not None:
                query = query.filter(ReadingList.list_type == list_type.value)

            if pinned_only:
                query = query.filter(ReadingList.is_pinned == True)  # noqa: E712

            # Order by pinned first, then by name
            query = query.order_by(
                desc(ReadingList.is_pinned),
                asc(ReadingList.name),
            )

            lists = query.limit(limit).all()

            return [self._to_list_summary(lst) for lst in lists]

    # ========================================================================
    # List Book Operations
    # ========================================================================

    def add_book_to_list(
        self, list_id: UUID, book_entry: ListBookCreate
    ) -> Optional[ListBookResponse]:
        """Add a book to a reading list.

        Args:
            list_id: List UUID
            book_entry: Book entry data

        Returns:
            Created entry or None if list not found
        """
        with self.db.get_session() as session:
            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            if not reading_list:
                return None

            # Check if book already in list
            existing = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id),
                ReadingListBook.book_id == str(book_entry.book_id),
            ).first()

            if existing:
                return self._to_list_book_response(existing)

            # Get next position
            max_pos_result = session.query(func.max(ReadingListBook.position)).filter(
                ReadingListBook.list_id == str(list_id)
            ).scalar()
            max_pos = max_pos_result if max_pos_result is not None else -1

            db_entry = ReadingListBook(
                list_id=str(list_id),
                book_id=str(book_entry.book_id),
                position=max_pos + 1,
                note=book_entry.note,
            )

            session.add(db_entry)
            reading_list.book_count += 1
            session.flush()

            return self._to_list_book_response(db_entry)

    def remove_book_from_list(self, list_id: UUID, book_id: UUID) -> bool:
        """Remove a book from a reading list.

        Args:
            list_id: List UUID
            book_id: Book UUID

        Returns:
            True if removed, False if not found
        """
        with self.db.get_session() as session:
            entry = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id),
                ReadingListBook.book_id == str(book_id),
            ).first()

            if not entry:
                return False

            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            session.delete(entry)

            if reading_list:
                reading_list.book_count = max(0, reading_list.book_count - 1)

            return True

    def get_list_books(self, list_id: UUID) -> list[ListBookWithDetails]:
        """Get all books in a reading list.

        Args:
            list_id: List UUID

        Returns:
            List of books with details
        """
        with self.db.get_session() as session:
            entries = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id)
            ).order_by(asc(ReadingListBook.position)).all()

            return [
                self._to_list_book_with_details(session, entry)
                for entry in entries
            ]

    def get_list_with_books(self, list_id: UUID) -> Optional[ReadingListWithBooks]:
        """Get a reading list with all its books.

        Args:
            list_id: List UUID

        Returns:
            List with books or None if not found
        """
        with self.db.get_session() as session:
            reading_list = session.query(ReadingList).filter(
                ReadingList.id == str(list_id)
            ).first()

            if not reading_list:
                return None

            entries = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id)
            ).order_by(asc(ReadingListBook.position)).all()

            books = [
                self._to_list_book_with_details(session, entry)
                for entry in entries
            ]

            return ReadingListWithBooks(
                list=self._to_list_response(reading_list),
                books=books,
            )

    def reorder_book(
        self, list_id: UUID, book_id: UUID, new_position: int
    ) -> Optional[ListBookResponse]:
        """Move a book to a new position in the list.

        Args:
            list_id: List UUID
            book_id: Book UUID
            new_position: New position (0-indexed)

        Returns:
            Updated entry or None if not found
        """
        with self.db.get_session() as session:
            entry = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id),
                ReadingListBook.book_id == str(book_id),
            ).first()

            if not entry:
                return None

            old_position = entry.position

            if new_position == old_position:
                return self._to_list_book_response(entry)

            # Get all other entries
            others = session.query(ReadingListBook).filter(
                ReadingListBook.list_id == str(list_id),
                ReadingListBook.book_id != str(book_id),
            ).order_by(asc(ReadingListBook.position)).all()

            # Shift positions
            if new_position > old_position:
                for other in others:
                    if old_position < other.position <= new_position:
                        other.position -= 1
            else:
                for other in others:
                    if new_position <= other.position < old_position:
                        other.position += 1

            entry.position = new_position
            session.flush()

            return self._to_list_book_response(entry)

    # ========================================================================
    # Recommendations
    # ========================================================================

    def get_recommendations(self, limit: int = 10) -> list[RecommendationSet]:
        """Get personalized book recommendations.

        Args:
            limit: Max recommendations per category

        Returns:
            List of recommendation sets
        """
        with self.db.get_session() as session:
            sets = []

            # 1. Books by favorite authors you haven't read
            author_recs = self._get_favorite_author_recommendations(session, limit)
            if author_recs:
                sets.append(RecommendationSet(
                    title="From Authors You Love",
                    description="Unread books by authors you've rated highly",
                    recommendations=author_recs,
                ))

            # 2. Highly rated in genres you like
            genre_recs = self._get_genre_recommendations(session, limit)
            if genre_recs:
                sets.append(RecommendationSet(
                    title="Top in Your Favorite Genres",
                    description="Highly rated books in genres you enjoy",
                    recommendations=genre_recs,
                ))

            # 3. Quick reads
            quick_recs = self._get_quick_read_recommendations(session, limit)
            if quick_recs:
                sets.append(RecommendationSet(
                    title="Quick Reads",
                    description="Short books you can finish in a day or two",
                    recommendations=quick_recs,
                ))

            # 4. Long on wishlist
            wishlist_recs = self._get_long_wishlist_recommendations(session, limit)
            if wishlist_recs:
                sets.append(RecommendationSet(
                    title="Waiting on Your Wishlist",
                    description="Books that have been on your list for a while",
                    recommendations=wishlist_recs,
                ))

            return sets

    def get_similar_books(self, book_id: UUID, limit: int = 5) -> list[SimilarBook]:
        """Find books similar to a given book.

        Args:
            book_id: Book UUID to find similar books for
            limit: Max similar books to return

        Returns:
            List of similar books
        """
        with self.db.get_session() as session:
            source_book = session.query(Book).filter(Book.id == str(book_id)).first()

            if not source_book:
                return []

            similar = []
            source_genres = source_book.get_genres() if source_book.genres else []

            # Find books by same author
            if source_book.author:
                same_author = session.query(Book).filter(
                    Book.author == source_book.author,
                    Book.id != str(book_id),
                    Book.status != BookStatus.COMPLETED.value,
                ).limit(limit).all()

                for book in same_author:
                    book_genres = book.get_genres() if book.genres else []
                    shared = set(source_genres) & set(book_genres)
                    similar.append(SimilarBook(
                        book_id=UUID(book.id),
                        book_title=book.title,
                        book_author=book.author,
                        similarity_score=0.9,  # Same author is highly similar
                        shared_genres=list(shared),
                        same_author=True,
                    ))

            # Find books with same genres
            if source_genres:
                for genre in source_genres:
                    genre_books = session.query(Book).filter(
                        Book.genres.ilike(f"%{genre}%"),
                        Book.id != str(book_id),
                        Book.author != source_book.author,
                        Book.status != BookStatus.COMPLETED.value,
                    ).limit(limit).all()

                    for book in genre_books:
                        # Check if already added
                        if any(s.book_id == UUID(book.id) for s in similar):
                            continue

                        book_genres = book.get_genres() if book.genres else []
                        shared = set(source_genres) & set(book_genres)
                        score = len(shared) / max(len(source_genres), 1) * 0.7

                        similar.append(SimilarBook(
                            book_id=UUID(book.id),
                            book_title=book.title,
                            book_author=book.author,
                            similarity_score=score,
                            shared_genres=list(shared),
                            same_author=False,
                        ))

            # Sort by similarity and limit
            similar.sort(key=lambda x: x.similarity_score, reverse=True)
            return similar[:limit]

    def get_genre_recommendations(self, genre: str, limit: int = 10) -> GenreRecommendations:
        """Get recommendations for a specific genre.

        Args:
            genre: Genre to get recommendations for
            limit: Max recommendations

        Returns:
            Genre recommendations
        """
        with self.db.get_session() as session:
            # Get highly rated unread books in this genre
            books = session.query(Book).filter(
                Book.genres.ilike(f"%{genre}%"),
                Book.status != BookStatus.COMPLETED.value,
            ).order_by(desc(Book.rating)).limit(limit).all()

            recommendations = []
            for book in books:
                recommendations.append(BookRecommendation(
                    book_id=UUID(book.id),
                    book_title=book.title,
                    book_author=book.author,
                    reason=RecommendationReason.HIGHLY_RATED_GENRE,
                    reason_display=f"Top rated in {genre}",
                    confidence=0.7,
                ))

            # Count unread in genre
            unread_count = session.query(Book).filter(
                Book.genres.ilike(f"%{genre}%"),
                Book.status != BookStatus.COMPLETED.value,
            ).count()

            # Average rating for read books in genre
            read_books = session.query(Book).filter(
                Book.genres.ilike(f"%{genre}%"),
                Book.status == BookStatus.COMPLETED.value,
                Book.rating.isnot(None),
            ).all()

            avg_rating = None
            if read_books:
                avg_rating = sum(b.rating for b in read_books) / len(read_books)

            return GenreRecommendations(
                genre=genre,
                top_rated=recommendations,
                unread_count=unread_count,
                average_rating=avg_rating,
            )

    def get_author_recommendations(self, author: str, limit: int = 10) -> AuthorRecommendations:
        """Get recommendations for books by an author.

        Args:
            author: Author name
            limit: Max recommendations

        Returns:
            Author recommendations
        """
        with self.db.get_session() as session:
            # Get read books by this author
            read_books = session.query(Book).filter(
                Book.author.ilike(f"%{author}%"),
                Book.status == BookStatus.COMPLETED.value,
            ).all()

            avg_rating = 0.0
            if read_books:
                rated = [b for b in read_books if b.rating]
                if rated:
                    avg_rating = sum(b.rating for b in rated) / len(rated)

            # Get unread books by this author
            unread = session.query(Book).filter(
                Book.author.ilike(f"%{author}%"),
                Book.status != BookStatus.COMPLETED.value,
            ).limit(limit).all()

            recommendations = []
            for book in unread:
                recommendations.append(BookRecommendation(
                    book_id=UUID(book.id),
                    book_title=book.title,
                    book_author=book.author,
                    reason=RecommendationReason.FAVORITE_AUTHOR,
                    reason_display=f"By {author}",
                    confidence=0.8 if avg_rating >= 4 else 0.6,
                    context=f"You've read {len(read_books)} books by this author",
                ))

            return AuthorRecommendations(
                author=author,
                books_read=len(read_books),
                average_rating=avg_rating,
                unread_books=recommendations,
            )

    def get_recommendation_stats(self) -> RecommendationStats:
        """Get statistics about recommendations.

        Returns:
            Recommendation statistics
        """
        with self.db.get_session() as session:
            # Total unread
            total_unread = session.query(Book).filter(
                Book.status != BookStatus.COMPLETED.value,
            ).count()

            # Highly rated unread (4+ stars from Goodreads or similar)
            highly_rated = session.query(Book).filter(
                Book.status != BookStatus.COMPLETED.value,
                Book.goodreads_avg_rating >= 4.0,
            ).count()

            # Favorite genres (from completed books)
            completed = session.query(Book).filter(
                Book.status == BookStatus.COMPLETED.value,
                Book.rating >= 4,
            ).all()

            genre_counts = Counter()
            for book in completed:
                if book.genres:
                    for genre in book.get_genres():
                        genre_counts[genre] += 1

            favorite_genres = [g for g, _ in genre_counts.most_common(5)]

            # Favorite authors
            author_ratings = {}
            for book in completed:
                if book.author and book.rating:
                    if book.author not in author_ratings:
                        author_ratings[book.author] = []
                    author_ratings[book.author].append(book.rating)

            # Authors with 2+ books rated 4+
            favorite_authors = [
                author for author, ratings in author_ratings.items()
                if len(ratings) >= 2 and sum(ratings) / len(ratings) >= 4
            ][:5]

            # Quick reads (under 200 pages)
            quick_reads = session.query(Book).filter(
                Book.status != BookStatus.COMPLETED.value,
                Book.page_count.isnot(None),
                Book.page_count <= 200,
            ).count()

            return RecommendationStats(
                total_unread=total_unread,
                highly_rated_unread=highly_rated,
                favorite_genres=favorite_genres,
                favorite_authors=favorite_authors,
                series_to_continue=0,  # Would need series module
                quick_reads_available=quick_reads,
            )

    # ========================================================================
    # Helper Methods - Recommendations
    # ========================================================================

    def _get_favorite_author_recommendations(
        self, session: Session, limit: int
    ) -> list[BookRecommendation]:
        """Get recommendations from favorite authors."""
        # Find authors you've rated highly
        high_rated = session.query(Book).filter(
            Book.status == BookStatus.COMPLETED.value,
            Book.rating >= 4,
        ).all()

        author_ratings = {}
        for book in high_rated:
            if book.author:
                if book.author not in author_ratings:
                    author_ratings[book.author] = []
                author_ratings[book.author].append(book.rating)

        # Find unread books by these authors
        recommendations = []
        for author, ratings in sorted(
            author_ratings.items(),
            key=lambda x: sum(x[1]) / len(x[1]),
            reverse=True,
        ):
            if len(ratings) >= 2:  # At least 2 books rated
                avg = sum(ratings) / len(ratings)
                unread = session.query(Book).filter(
                    Book.author == author,
                    Book.status != BookStatus.COMPLETED.value,
                ).limit(3).all()

                for book in unread:
                    recommendations.append(BookRecommendation(
                        book_id=UUID(book.id),
                        book_title=book.title,
                        book_author=book.author,
                        reason=RecommendationReason.FAVORITE_AUTHOR,
                        reason_display=f"You love {author}",
                        confidence=min(0.95, avg / 5),
                        context=f"Avg rating: {avg:.1f}/5 from {len(ratings)} books",
                    ))

            if len(recommendations) >= limit:
                break

        return recommendations[:limit]

    def _get_genre_recommendations(
        self, session: Session, limit: int
    ) -> list[BookRecommendation]:
        """Get recommendations from favorite genres."""
        # Find genres you've rated highly
        high_rated = session.query(Book).filter(
            Book.status == BookStatus.COMPLETED.value,
            Book.rating >= 4,
            Book.genres.isnot(None),
        ).all()

        genre_ratings = {}
        for book in high_rated:
            for genre in book.get_genres():
                if genre not in genre_ratings:
                    genre_ratings[genre] = []
                genre_ratings[genre].append(book.rating)

        # Find highly rated unread books in these genres
        recommendations = []
        for genre, ratings in sorted(
            genre_ratings.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:3]:  # Top 3 genres
            unread = session.query(Book).filter(
                Book.genres.ilike(f"%{genre}%"),
                Book.status != BookStatus.COMPLETED.value,
            ).order_by(desc(Book.goodreads_avg_rating)).limit(5).all()

            for book in unread:
                if not any(r.book_id == UUID(book.id) for r in recommendations):
                    recommendations.append(BookRecommendation(
                        book_id=UUID(book.id),
                        book_title=book.title,
                        book_author=book.author,
                        reason=RecommendationReason.HIGHLY_RATED_GENRE,
                        reason_display=f"Top {genre} book",
                        confidence=0.7,
                        context=f"Goodreads: {book.goodreads_avg_rating:.1f}/5" if book.goodreads_avg_rating else None,
                    ))

            if len(recommendations) >= limit:
                break

        return recommendations[:limit]

    def _get_quick_read_recommendations(
        self, session: Session, limit: int
    ) -> list[BookRecommendation]:
        """Get quick read recommendations."""
        quick_reads = session.query(Book).filter(
            Book.status != BookStatus.COMPLETED.value,
            Book.page_count.isnot(None),
            Book.page_count <= 200,
        ).order_by(desc(Book.goodreads_avg_rating)).limit(limit).all()

        recommendations = []
        for book in quick_reads:
            recommendations.append(BookRecommendation(
                book_id=UUID(book.id),
                book_title=book.title,
                book_author=book.author,
                reason=RecommendationReason.QUICK_READ,
                reason_display="Quick read",
                confidence=0.6,
                context=f"{book.page_count} pages",
            ))

        return recommendations

    def _get_long_wishlist_recommendations(
        self, session: Session, limit: int
    ) -> list[BookRecommendation]:
        """Get books that have been on wishlist a long time."""
        wishlist = session.query(Book).filter(
            Book.status == BookStatus.WISHLIST.value,
        ).order_by(asc(Book.date_added)).limit(limit).all()

        recommendations = []
        for book in wishlist:
            recommendations.append(BookRecommendation(
                book_id=UUID(book.id),
                book_title=book.title,
                book_author=book.author,
                reason=RecommendationReason.LONG_WISHLIST,
                reason_display="Long on wishlist",
                confidence=0.5,
                context=f"Added: {book.date_added}" if book.date_added else None,
            ))

        return recommendations

    # ========================================================================
    # Helper Methods - Conversion
    # ========================================================================

    def _to_list_response(self, reading_list: ReadingList) -> ReadingListResponse:
        """Convert model to response schema."""
        return ReadingListResponse(
            id=UUID(reading_list.id),
            name=reading_list.name,
            description=reading_list.description,
            list_type=ListType(reading_list.list_type),
            type_display=reading_list.type_display,
            is_public=reading_list.is_public,
            is_pinned=reading_list.is_pinned,
            is_auto=reading_list.is_auto,
            color=reading_list.color,
            icon=reading_list.icon,
            book_count=reading_list.book_count,
            created_at=datetime.fromisoformat(reading_list.created_at),
            updated_at=datetime.fromisoformat(reading_list.updated_at),
        )

    def _to_list_summary(self, reading_list: ReadingList) -> ReadingListSummary:
        """Convert model to summary schema."""
        return ReadingListSummary(
            id=UUID(reading_list.id),
            name=reading_list.name,
            list_type=ListType(reading_list.list_type),
            type_display=reading_list.type_display,
            is_pinned=reading_list.is_pinned,
            book_count=reading_list.book_count,
            icon=reading_list.icon,
        )

    def _to_list_book_response(self, entry: ReadingListBook) -> ListBookResponse:
        """Convert model to response schema."""
        return ListBookResponse(
            id=UUID(entry.id),
            list_id=UUID(entry.list_id),
            book_id=UUID(entry.book_id),
            position=entry.position,
            note=entry.note,
            added_at=datetime.fromisoformat(entry.added_at),
        )

    def _to_list_book_with_details(
        self, session: Session, entry: ReadingListBook
    ) -> ListBookWithDetails:
        """Convert model to response with book details."""
        book = session.query(Book).filter(Book.id == entry.book_id).first()

        return ListBookWithDetails(
            id=UUID(entry.id),
            list_id=UUID(entry.list_id),
            book_id=UUID(entry.book_id),
            position=entry.position,
            note=entry.note,
            added_at=datetime.fromisoformat(entry.added_at),
            book_title=book.title if book else None,
            book_author=book.author if book else None,
            book_status=book.status if book else None,
            book_rating=book.rating if book else None,
        )
