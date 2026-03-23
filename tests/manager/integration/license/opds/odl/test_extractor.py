from __future__ import annotations

import datetime
from unittest.mock import MagicMock

import pytest

from palace.manager.data_layer.identifier import IdentifierData
from palace.manager.data_layer.link import LinkData
from palace.manager.integration.license.opds.odl.constants import FEEDBOOKS_AUDIO
from palace.manager.integration.license.opds.odl.extractor import OPDS2WithODLExtractor
from palace.manager.opds import opds2, rwpm
from palace.manager.opds.lcp.status import LoanStatus
from palace.manager.opds.odl.info import Checkouts, LicenseInfo, LicenseStatus
from palace.manager.opds.odl.odl import License, LicenseMetadata, Publication
from palace.manager.opds.odl.protection import Protection
from palace.manager.opds.odl.terms import Terms
from palace.manager.opds.opds2 import PublicationFeedNoValidation, StrictLink
from palace.manager.opds.schema_org import Audience
from palace.manager.sqlalchemy.constants import EditionConstants, MediaTypes
from palace.manager.sqlalchemy.model.contributor import Contributor
from palace.manager.sqlalchemy.model.edition import Edition
from palace.manager.sqlalchemy.model.licensing import DeliveryMechanism, RightsStatus
from palace.manager.sqlalchemy.model.resource import Hyperlink
from palace.manager.util.datetime_helpers import utc_now
from tests.fixtures.files import OPDS2FilesFixture


class ODLExtractorTestFixture:
    """Factory functions for creating ODL extractor test objects."""

    def __init__(self) -> None:
        self.license_identifier: str = "test-license-123"
        self.publication_identifier: str = "urn:isbn:9780306406157"

    def license_links(self) -> list[StrictLink]:
        """Create standard license links for testing."""
        return [
            StrictLink(
                rel=rwpm.LinkRelations.self,
                type=LicenseInfo.content_type(),
                href="http://example.org/license",
            ),
            StrictLink(
                rel=opds2.AcquisitionLinkRelations.borrow,
                type=LoanStatus.content_type(),
                href="http://example.org/borrow",
            ),
        ]

    def license(
        self,
        license_format: str = "",
        protection: Protection | None = None,
        terms: Terms | None = None,
    ) -> License:
        """Create a License with the given format, protection, and terms."""
        if protection is None:
            protection = Protection(
                format=[DeliveryMechanism.LCP_DRM, DeliveryMechanism.ADOBE_DRM]
            )
        if terms is None:
            terms = Terms(concurrency=1)
        return License(
            metadata=LicenseMetadata(
                identifier=self.license_identifier,
                created=utc_now(),
                format=license_format,
                terms=terms,
                protection=protection,
            ),
            links=self.license_links(),
        )

    def publication(self, license: License) -> Publication:
        """Create a Publication with the given license."""
        return Publication(
            metadata=opds2.PublicationMetadata(
                type="http://schema.org/Book",
                identifier=self.publication_identifier,
                title="Test Book",
            ),
            images=[
                opds2.Link(
                    href="http://example.org/cover.jpg",
                    type="image/jpeg",
                )
            ],
            links=[],
            licenses=[license],
        )

    def extractor(
        self,
        skipped_license_formats: set[str] | None = None,
    ) -> OPDS2WithODLExtractor[Publication]:
        """Create an OPDS2WithODLExtractor for testing."""
        return OPDS2WithODLExtractor(
            parse_publication=MagicMock(),
            base_url="http://example.org",
            data_source="Test Source",
            skipped_license_formats=skipped_license_formats,
        )

    def license_info(
        self,
        license_format: str = "",
        terms: Terms | None = None,
        checkouts: Checkouts | None = None,
    ) -> LicenseInfo:
        """Create a LicenseInfo document for testing."""
        if terms is None:
            terms = Terms(concurrency=1)
        if checkouts is None:
            checkouts = Checkouts(available=1)
        return LicenseInfo(
            identifier=self.license_identifier,
            status=LicenseStatus.available,
            checkouts=checkouts,
            terms=terms,
            format=license_format,
        )

    def identifier_data(self) -> IdentifierData:
        """Create IdentifierData from the publication identifier."""
        return IdentifierData.parse_urn(self.publication_identifier)


@pytest.fixture(scope="class")
def odl_extractor_fixture() -> ODLExtractorTestFixture:
    """Fixture providing factory functions for ODL extractor tests."""
    return ODLExtractorTestFixture()


class TestOPDS2WithODLExtractor:
    def test__extract_odl_license_data(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        # Expiry mismatch makes license unavailable
        info_terms = Terms(expires=utc_now() + datetime.timedelta(days=1))
        license_terms = Terms(expires=utc_now() + datetime.timedelta(days=2))
        license_info = odl_extractor_fixture.license_info(terms=info_terms)
        odl_license = odl_extractor_fixture.license(terms=license_terms)

        license_data = OPDS2WithODLExtractor._extract_odl_license_data(
            license_info, odl_license
        )
        assert license_data is not None
        assert license_data.status == LicenseStatus.unavailable

        # Concurrency mismatch makes license unavailable
        license_info = odl_extractor_fixture.license_info(terms=Terms(concurrency=12))
        odl_license = odl_extractor_fixture.license(terms=Terms(concurrency=11))

        license_data = OPDS2WithODLExtractor._extract_odl_license_data(
            license_info, odl_license
        )
        assert license_data is not None
        assert license_data.status == LicenseStatus.unavailable

        # Good data returns LicenseData
        license_info = odl_extractor_fixture.license_info()
        odl_license = odl_extractor_fixture.license()

        license_data = OPDS2WithODLExtractor._extract_odl_license_data(
            license_info, odl_license
        )
        assert license_data is not None
        assert license_data.status == LicenseStatus.available

    def test__extract_contributor_roles(self) -> None:
        _extract_contributor_roles = OPDS2WithODLExtractor._extract_contributor_roles

        # If there are no roles, the function returns the default
        assert _extract_contributor_roles([], Contributor.Role.AUTHOR) == [
            Contributor.Role.AUTHOR
        ]

        # If the role is unknown, the default is used
        assert _extract_contributor_roles(["invalid"], Contributor.Role.AUTHOR) == [
            Contributor.Role.AUTHOR
        ]

        # Roles are not duplicated
        assert _extract_contributor_roles(
            [Contributor.Role.AUTHOR, Contributor.Role.AUTHOR], Contributor.Role.AUTHOR
        ) == [Contributor.Role.AUTHOR]
        assert _extract_contributor_roles(
            ["invalid", "invalid"], Contributor.Role.AUTHOR
        ) == [Contributor.Role.AUTHOR]

        # Role lookup is not case-sensitive
        assert _extract_contributor_roles(["aUtHoR"], Contributor.Role.ILLUSTRATOR) == [
            Contributor.Role.AUTHOR
        ]

        # Roles can be looked up via marc codes
        assert _extract_contributor_roles(["AUT"], Contributor.Role.ILLUSTRATOR) == [
            Contributor.Role.AUTHOR
        ]

    @pytest.mark.parametrize(
        "published,expected",
        [
            pytest.param(
                datetime.datetime(2015, 9, 29, 17, 0, tzinfo=datetime.UTC),
                datetime.date(2015, 9, 29),
                id="datetime with time info",
            ),
            pytest.param(
                datetime.datetime(2015, 9, 29, 0, 0),
                datetime.date(2015, 9, 29),
                id="datetime with no time info",
            ),
            pytest.param(
                datetime.date(2015, 9, 29),
                datetime.date(2015, 9, 29),
                id="date",
            ),
            pytest.param(
                None,
                None,
                id="none",
            ),
        ],
    )
    def test__extract_published_date(
        self,
        published: datetime.datetime | datetime.date | None,
        expected: datetime.date | None,
    ) -> None:
        assert OPDS2WithODLExtractor._extract_published_date(published) == expected

    def test_feed_next_url(
        self,
        opds2_files_fixture: OPDS2FilesFixture,
    ) -> None:
        # No next links
        feed = PublicationFeedNoValidation.model_validate_json(
            opds2_files_fixture.sample_data("feed.json")
        )
        assert OPDS2WithODLExtractor.feed_next_url(feed) is None

        # Feed has next link
        feed = PublicationFeedNoValidation.model_validate_json(
            opds2_files_fixture.sample_data("feed2.json")
        )
        assert (
            OPDS2WithODLExtractor.feed_next_url(feed)
            == "http://bookshelf-feed-demo.us-east-1.elasticbeanstalk.com/v1/publications?page=2&limit=100"
        )

    @pytest.mark.parametrize(
        "medium, license_format, expected_drm, expected_content_type",
        [
            pytest.param(
                EditionConstants.AUDIO_MEDIUM,
                FEEDBOOKS_AUDIO,
                DeliveryMechanism.FEEDBOOKS_AUDIOBOOK_DRM,
                MediaTypes.AUDIOBOOK_MANIFEST_MEDIA_TYPE,
                id="feedbooks-audio",
            ),
            pytest.param(
                EditionConstants.AUDIO_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                DeliveryMechanism.STREAMING_DRM,
                DeliveryMechanism.STREAMING_AUDIO_CONTENT_TYPE,
                id="audio-html",
            ),
            pytest.param(
                EditionConstants.BOOK_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                DeliveryMechanism.STREAMING_DRM,
                DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE,
                id="text-html",
            ),
            pytest.param(
                EditionConstants.PERIODICAL_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                DeliveryMechanism.STREAMING_DRM,
                DeliveryMechanism.STREAMING_PERIODICAL_CONTENT_TYPE,
                id="periodical-html",
            ),
            pytest.param(
                None,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                DeliveryMechanism.STREAMING_DRM,
                DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE,
                id="none-medium-defaults-to-text",
            ),
        ],
    )
    def test__extract_odl_circulation_data_license_formats_mapping(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
        medium: str | None,
        license_format: str,
        expected_drm: str | None,
        expected_content_type: str,
    ) -> None:
        """
        Test that special license formats (FEEDBOOKS_AUDIO, text/html) are correctly
        mapped to their appropriate content types and DRM schemes based on the
        publication medium, ignoring any protection formats specified in the license.
        """
        # The fixture's default protection includes multiple DRM schemes that should
        # be IGNORED for these special mapped formats.
        odl_license = odl_extractor_fixture.license(license_format)
        publication = odl_extractor_fixture.publication(odl_license)
        extractor = odl_extractor_fixture.extractor()

        circulation_data = extractor._extract_odl_circulation_data(
            publication=publication,
            license_info_documents={
                odl_extractor_fixture.license_identifier: odl_extractor_fixture.license_info(
                    license_format
                )
            },
            identifier=odl_extractor_fixture.identifier_data(),
            medium=medium,
        )

        # Ensure that we got one correct format.
        [format_data] = circulation_data.formats
        assert format_data.content_type == expected_content_type
        assert format_data.drm_scheme == expected_drm

    @pytest.mark.parametrize(
        "medium, license_format, skipped_formats",
        [
            pytest.param(
                EditionConstants.AUDIO_MEDIUM,
                FEEDBOOKS_AUDIO,
                {FEEDBOOKS_AUDIO},
                id="skip-feedbooks-audio",
            ),
            pytest.param(
                EditionConstants.AUDIO_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                {DeliveryMechanism.STREAMING_AUDIO_CONTENT_TYPE},
                id="skip-streaming-audio",
            ),
            pytest.param(
                EditionConstants.BOOK_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                {DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE},
                id="skip-streaming-text",
            ),
            pytest.param(
                EditionConstants.PERIODICAL_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                {DeliveryMechanism.STREAMING_PERIODICAL_CONTENT_TYPE},
                id="skip-streaming-periodical",
            ),
            pytest.param(
                EditionConstants.AUDIO_MEDIUM,
                MediaTypes.TEXT_HTML_MEDIA_TYPE,
                {MediaTypes.TEXT_HTML_MEDIA_TYPE},
                id="skip-text-html",
            ),
        ],
    )
    def test__extract_odl_circulation_data_skipped_license_formats(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
        medium: str,
        license_format: str,
        skipped_formats: set[str],
    ) -> None:
        """
        Test that skipped license formats are omitted from circulation data formats.
        """
        odl_license = odl_extractor_fixture.license(license_format)
        publication = odl_extractor_fixture.publication(odl_license)
        extractor = odl_extractor_fixture.extractor(
            skipped_license_formats=skipped_formats
        )

        circulation_data = extractor._extract_odl_circulation_data(
            publication=publication,
            license_info_documents={
                odl_extractor_fixture.license_identifier: odl_extractor_fixture.license_info(
                    license_format
                )
            },
            identifier=odl_extractor_fixture.identifier_data(),
            medium=medium,
        )

        assert circulation_data.formats == []
        assert circulation_data.licenses is not None
        assert len(circulation_data.licenses) == 1

    def test__extract_odl_circulation_data_empty_protection_formats(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """
        Test that when protection.formats is empty, the format is added with drm_scheme=None.
        """
        license_format = MediaTypes.EPUB_MEDIA_TYPE

        # Explicitly pass empty protection to test the no-DRM case
        odl_license = odl_extractor_fixture.license(
            license_format, protection=Protection(format=[])
        )
        publication = odl_extractor_fixture.publication(odl_license)
        extractor = odl_extractor_fixture.extractor()

        circulation_data = extractor._extract_odl_circulation_data(
            publication=publication,
            license_info_documents={
                odl_extractor_fixture.license_identifier: odl_extractor_fixture.license_info(
                    license_format
                )
            },
            identifier=odl_extractor_fixture.identifier_data(),
            medium=EditionConstants.BOOK_MEDIUM,
        )

        # Ensure we got exactly one format with no DRM
        assert len(circulation_data.formats) == 1
        [format_data] = circulation_data.formats
        assert format_data.content_type == MediaTypes.EPUB_MEDIA_TYPE
        assert format_data.drm_scheme is None
        assert format_data.rights_uri == RightsStatus.IN_COPYRIGHT

    def test__extract_schema_org_subjects_typical_age_range(self) -> None:
        """Test extraction of schema:typicalAgeRange into AGE_RANGE subject."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            typical_age_range="8-12",
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        assert len(subjects) == 1
        assert subjects[0].type == "schema:typicalAgeRange"
        assert subjects[0].identifier == "8-12"
        assert subjects[0].name == "8-12"

    def test__extract_schema_org_subjects_audience_type(self) -> None:
        """Test extraction of schema:audience.audienceType into FREEFORM_AUDIENCE subject."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            audience=Audience(
                type="schema:PeopleAudience",
                audience_type="Children",
            ),
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        assert len(subjects) == 1
        assert subjects[0].type == "schema:audience"
        assert subjects[0].identifier == "Children"
        assert subjects[0].name == "Children"

    def test__extract_schema_org_subjects_audience_age_range(self) -> None:
        """Test extraction of suggested min/max age from schema:audience."""
        # Both min and max age
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            audience=Audience(
                type="schema:PeopleAudience",
                suggested_min_age=5,
                suggested_max_age=10,
            ),
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        assert len(subjects) == 1
        assert subjects[0].type == "schema:typicalAgeRange"
        assert subjects[0].identifier == "5-10"

        # Only min age
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            audience=Audience(
                type="schema:PeopleAudience",
                suggested_min_age=8,
            ),
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        assert len(subjects) == 1
        assert subjects[0].identifier == "8-"

        # Only max age
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            audience=Audience(
                type="schema:PeopleAudience",
                suggested_max_age=12,
            ),
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        assert len(subjects) == 1
        assert subjects[0].identifier == "-12"

    def test__extract_schema_org_subjects_combined(self) -> None:
        """Test extraction when multiple schema.org fields are present."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            typical_age_range="5-12",
            audience=Audience(
                type="schema:PeopleAudience",
                audience_type="Children",
                suggested_min_age=6,
                suggested_max_age=11,
            ),
        )

        subjects = OPDS2WithODLExtractor._extract_schema_org_subjects(metadata)

        # Should have 3 subjects: typical_age_range, audience_type, and suggested age range
        assert len(subjects) == 3

        # Check types are present
        types = {s.type for s in subjects}
        assert "schema:typicalAgeRange" in types
        assert "schema:audience" in types

        # Check identifiers
        identifiers = {s.identifier for s in subjects}
        assert "5-12" in identifiers  # from typical_age_range
        assert "Children" in identifiers  # from audience_type
        assert "6-11" in identifiers  # from suggested ages

    def test__extract_series_from_belongs_to_with_series_and_position(self) -> None:
        """belongsTo.series with name and position extracts both correctly."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            belongs_to=rwpm.BelongsTo(
                series_data=rwpm.Contributor(name="My Series", position=3)
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "My Series"
        assert position == 3
        assert series_identifier is None

    def test__extract_series_from_belongs_to_no_position(self) -> None:
        """belongsTo.series with no position returns None for position."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
            belongs_to=rwpm.BelongsTo(
                series_data=rwpm.Contributor(name="Positionless Series")
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Positionless Series"
        assert position is None
        assert series_identifier is None

    def test__extract_series_from_belongs_to_no_series(self) -> None:
        """Publication with no belongsTo.series returns (None, None)."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/Book",
            identifier="urn:isbn:9780306406157",
            title="Test Book",
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series is None
        assert position is None
        assert series_identifier is None

    def test__extract_series_from_belongs_to_legacy_series_alias(self) -> None:
        """belongsTo.Series (legacy key) is treated the same as belongsTo.series."""
        metadata = opds2.PublicationMetadata.model_validate(
            {
                "@type": "http://schema.org/PublicationIssue",
                "identifier": "urn:isbn:9780306406157",
                "title": "Test Periodical",
                "belongsTo": {
                    "Series": {
                        "name": "Legacy Series",
                        "position": 9,
                    }
                },
            }
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Legacy Series"
        assert position == 9
        assert series_identifier is None

    def test__extract_series_from_belongs_to_periodical_precedence(self) -> None:
        """belongsTo.periodical takes precedence over Magazine and series."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                periodical_data=rwpm.Contributor(
                    name="Official Periodical",
                    identifier="urn:issn:official_periodical",
                    position=7,
                ),
                magazine_data=rwpm.Contributor(name="Legacy Magazine", position=4),
                series_data=rwpm.Contributor(name="Series Name", position=1),
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Official Periodical"
        assert position == 7
        assert series_identifier == "urn:issn:official_periodical"

    def test__extract_series_from_belongs_to_magazine_fallback(self) -> None:
        """belongsTo.Magazine is used when periodical is absent."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                magazine_data=rwpm.Contributor(name="Legacy Magazine", position=4),
                series_data=rwpm.Contributor(name="Series Name", position=1),
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Legacy Magazine"
        assert position == 4
        assert series_identifier is None

    def test__extract_series_from_belongs_to_journal_fallback(self) -> None:
        """belongsTo.journal is used when periodical and magazine are absent."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                journal_data=rwpm.Contributor(name="Journal Name", position=6),
                series_data=rwpm.Contributor(name="Series Name", position=1),
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Journal Name"
        assert position == 6
        assert series_identifier is None

    def test__extract_bibliographic_data_periodical_series_end_to_end(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """Periodical belongsTo metadata is carried into BibliographicData."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier=odl_extractor_fixture.publication_identifier,
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                periodical_data=rwpm.Contributor(
                    name="Official Periodical",
                    identifier="urn:issn:official_periodical",
                    position=12,
                )
            ),
        )
        publication = opds2.Publication(
            metadata=metadata,
            images=[
                opds2.Link(
                    href="http://example.org/cover.jpg",
                    rel=rwpm.LinkRelations.cover,
                    type="image/jpeg",
                )
            ],
            links=[
                opds2.StrictLink(
                    rel=opds2.AcquisitionLinkRelations.open_access,
                    type="application/epub+zip",
                    href="http://example.org/acquisition",
                )
            ],
        )
        extractor = odl_extractor_fixture.extractor()

        bibliographic_data = extractor._extract_bibliographic_data(
            publication=publication,
            identifier=odl_extractor_fixture.identifier_data(),
            medium=EditionConstants.PERIODICAL_MEDIUM,
        )

        assert bibliographic_data.title == "Test Periodical"
        assert bibliographic_data.medium == EditionConstants.PERIODICAL_MEDIUM
        assert bibliographic_data.series == "Official Periodical"
        assert bibliographic_data.series_identifier == "urn:issn:official_periodical"
        assert bibliographic_data.series_position == 12

    def test__extract_series_from_belongs_to_magazine_volume_fallback(self) -> None:
        """belongsTo.magazine with volume but no position uses volume as series_position."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Magazine Issue",
            belongs_to=rwpm.BelongsTo(
                magazine_data=rwpm.Contributor(name="American Scientist", volume=2025)
            ),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "American Scientist"
        assert position == 2025
        assert series_identifier is None

    def test__extract_series_from_belongs_to_contains_issue_position(self) -> None:
        """contains.issue.position is used as series_position when present."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:emagazines:issue:american_scientist:20250812",
            title="September/October 2025",
            belongs_to=rwpm.BelongsTo(
                magazine_data=rwpm.Contributor(name="American Scientist", volume=2025)
            ),
            contains=rwpm.Contains(issue=rwpm.Issue(position=224)),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "American Scientist"
        assert position == 224
        assert series_identifier is None

    def test__extract_series_from_belongs_to_contains_overrides_contributor_position(
        self,
    ) -> None:
        """contains.issue.position takes precedence over contributor.position."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                periodical_data=rwpm.Contributor(name="Science Journal", position=5)
            ),
            contains=rwpm.Contains(issue=rwpm.Issue(position=52)),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "Science Journal"
        assert position == 52
        assert series_identifier is None

    def test__extract_series_from_belongs_to_contains_no_position(self) -> None:
        """contains present but issue.position absent falls back to contributor."""
        metadata = opds2.PublicationMetadata(
            type="http://schema.org/PublicationIssue",
            identifier="urn:isbn:9780306406157",
            title="Test Periodical",
            belongs_to=rwpm.BelongsTo(
                magazine_data=rwpm.Contributor(name="People", position=3)
            ),
            contains=rwpm.Contains(issue=rwpm.Issue()),
        )

        series, position, series_identifier = (
            OPDS2WithODLExtractor._extract_series_from_belongs_to(metadata)
        )

        assert series == "People"
        assert position == 3
        assert series_identifier is None

    # -------------------------------------------------------------------------
    # application/webpub+json streaming acquisition tests
    # -------------------------------------------------------------------------

    def test__webpub_streaming_format_data_returns_none_for_non_webpub(self) -> None:
        """Non-webpub links return None."""
        link = LinkData(
            rel=Hyperlink.GENERIC_OPDS_ACQUISITION,
            media_type=MediaTypes.EPUB_MEDIA_TYPE,
            href="http://example.com/book.epub",
        )
        result = OPDS2WithODLExtractor._webpub_streaming_format_data(
            link, Edition.BOOK_MEDIUM, RightsStatus.IN_COPYRIGHT
        )
        assert result is None

    @pytest.mark.parametrize(
        "medium,expected_content_type",
        [
            pytest.param(
                Edition.PERIODICAL_MEDIUM,
                DeliveryMechanism.STREAMING_PERIODICAL_CONTENT_TYPE,
                id="periodical",
            ),
            pytest.param(
                Edition.AUDIO_MEDIUM,
                DeliveryMechanism.STREAMING_AUDIO_CONTENT_TYPE,
                id="audio",
            ),
            pytest.param(
                Edition.BOOK_MEDIUM,
                DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE,
                id="book defaults to text",
            ),
            pytest.param(
                None,
                DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE,
                id="no medium defaults to text",
            ),
        ],
    )
    def test__webpub_streaming_format_data_maps_medium_to_content_type(
        self, medium: str | None, expected_content_type: str
    ) -> None:
        """application/webpub+json is translated to the correct streaming content type."""
        link = LinkData(
            rel=Hyperlink.GENERIC_OPDS_ACQUISITION,
            media_type=MediaTypes.WEBPUB_MANIFEST_MEDIA_TYPE,
            href="http://example.com/catalog/39696",
        )
        result = OPDS2WithODLExtractor._webpub_streaming_format_data(
            link, medium, RightsStatus.IN_COPYRIGHT
        )
        assert result is not None
        assert result.content_type == expected_content_type
        assert result.drm_scheme == DeliveryMechanism.STREAMING_DRM
        assert result.link == link

    def test__extract_opds2_formats_webpub_periodical(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """application/webpub+json in a periodical publication becomes STREAMING_PERIODICAL."""
        extractor = odl_extractor_fixture.extractor()
        links = [
            opds2.StrictLink(
                rel="http://opds-spec.org/acquisition",
                type=MediaTypes.WEBPUB_MANIFEST_MEDIA_TYPE,
                href="http://example.com/catalog/39696",
            )
        ]

        formats = extractor._extract_opds2_formats(
            links,
            rights_uri=RightsStatus.IN_COPYRIGHT,
            medium=Edition.PERIODICAL_MEDIUM,
        )

        assert len(formats) == 1
        assert formats[0].content_type == DeliveryMechanism.STREAMING_PERIODICAL_CONTENT_TYPE
        assert formats[0].drm_scheme == DeliveryMechanism.STREAMING_DRM

    def test__extract_opds2_formats_webpub_book_medium(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """application/webpub+json with book medium falls back to STREAMING_TEXT."""
        extractor = odl_extractor_fixture.extractor()
        links = [
            opds2.StrictLink(
                rel="http://opds-spec.org/acquisition",
                type=MediaTypes.WEBPUB_MANIFEST_MEDIA_TYPE,
                href="http://example.com/catalog/12345",
            )
        ]

        formats = extractor._extract_opds2_formats(
            links,
            rights_uri=RightsStatus.IN_COPYRIGHT,
            medium=Edition.BOOK_MEDIUM,
        )

        assert len(formats) == 1
        assert formats[0].content_type == DeliveryMechanism.STREAMING_TEXT_CONTENT_TYPE
        assert formats[0].drm_scheme == DeliveryMechanism.STREAMING_DRM

    def test__extract_opds2_formats_non_webpub_unaffected(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """Non-webpub acquisition links still go through the normal format path."""
        extractor = odl_extractor_fixture.extractor()
        links = [
            opds2.StrictLink(
                rel="http://opds-spec.org/acquisition/open-access",
                type=MediaTypes.EPUB_MEDIA_TYPE,
                href="http://example.com/book.epub",
            )
        ]

        # open-access link — should be skipped by _extract_opds2_formats
        formats = extractor._extract_opds2_formats(
            links,
            rights_uri=RightsStatus.IN_COPYRIGHT,
            medium=Edition.BOOK_MEDIUM,
        )

        assert len(formats) == 0

    def test_publication_bibliographic_webpub_periodical_when_type_is_book(
        self,
        odl_extractor_fixture: ODLExtractorTestFixture,
    ) -> None:
        """A webpub acquisition link drives periodical medium even with @type=Book.

        This covers feeds that incorrectly set metadata @type to Book while still
        exposing periodical content through non-open-access webpub acquisition links.
        """
        extractor = odl_extractor_fixture.extractor()
        identifier = odl_extractor_fixture.identifier_data()
        publication = opds2.Publication(
            metadata=opds2.PublicationMetadata(
                type="http://schema.org/Book",
                identifier=odl_extractor_fixture.publication_identifier,
                title="Template Webpub Periodical",
            ),
            links=[
                opds2.StrictLink(
                    rel="http://opds-spec.org/acquisition",
                    type=MediaTypes.WEBPUB_MANIFEST_MEDIA_TYPE,
                    href="http://example.com/catalog/39696",
                    templated=True,
                )
            ],
            images=[],
        )

        # Non-variable hrefs should not remain templated, even if feed says so.
        assert publication.links[0].templated is False

        bibliographic = extractor.publication_bibliographic(identifier, publication)

        assert bibliographic.medium == Edition.PERIODICAL_MEDIUM
        assert bibliographic.circulation is not None
        assert len(bibliographic.circulation.formats) == 1

        [format_data] = bibliographic.circulation.formats
        assert format_data.content_type == DeliveryMechanism.STREAMING_PERIODICAL_CONTENT_TYPE
        assert format_data.drm_scheme == DeliveryMechanism.STREAMING_DRM
        assert format_data.rights_uri == RightsStatus.IN_COPYRIGHT
