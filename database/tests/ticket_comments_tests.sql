-- =============================================================================
-- ticket_comments schema tests
-- ALE Ticket Management Tool — Phase 1 Database Foundation
--
-- Run via psql with:  psql -v ON_ERROR_STOP=1 -f ticket_comments_tests.sql
--
-- The entire temporary database is disposable; cleanup is handled by the
-- PowerShell runner, not by transaction rollback.
-- =============================================================================


-- =============================================================================
\echo '-- TEST SETUP: inserting prerequisite users and ticket'
-- =============================================================================

INSERT INTO users (name, email, password_hash, role)
VALUES ('Comment Requester', 'comment.requester@example.com', 'dummy-test-hash', 'requester');

INSERT INTO users (name, email, password_hash, role)
VALUES ('Comment Engineer', 'comment.engineer@example.com', 'dummy-test-hash', 'support_engineer');

INSERT INTO tickets (title, description, requester_id)
SELECT
    'Comment test ticket',
    'Used to validate ticket comments.',
    id
FROM users
WHERE email = 'comment.requester@example.com';


-- =============================================================================
\echo '-- VALID COMMENT TESTS'
-- =============================================================================

\echo '-- VALID 1: public comment from requester'
INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
SELECT
    t.id,
    u.id,
    'Public comment from requester.',
    'public'
FROM tickets t
CROSS JOIN users u
WHERE t.title = 'Comment test ticket'
  AND u.email = 'comment.requester@example.com';

\echo '-- VALID 2: internal comment from support engineer'
INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
SELECT
    t.id,
    u.id,
    'Internal note visible only to staff.',
    'internal'
FROM tickets t
CROSS JOIN users u
WHERE t.title = 'Comment test ticket'
  AND u.email = 'comment.engineer@example.com';

\echo '-- VALID 3: system comment with null author'
INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
SELECT
    id,
    NULL,
    'Status changed to Open by the system.',
    'system'
FROM tickets
WHERE title = 'Comment test ticket';

\echo '-- VALID 4: system comment with a named author'
INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
SELECT
    t.id,
    u.id,
    'System note attributed to engineer.',
    'system'
FROM tickets t
CROSS JOIN users u
WHERE t.title = 'Comment test ticket'
  AND u.email = 'comment.engineer@example.com';

\echo '-- VALID 5: comment without specifying comment_type — must default to public'
INSERT INTO ticket_comments (ticket_id, author_id, comment_text)
SELECT
    t.id,
    u.id,
    'Comment using default type.'
FROM tickets t
CROSS JOIN users u
WHERE t.title = 'Comment test ticket'
  AND u.email = 'comment.requester@example.com';

DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM ticket_comments
    WHERE comment_text = 'Comment using default type.'
      AND comment_type = 'public';

    IF v_count <> 1 THEN
        RAISE EXCEPTION 'FAIL: default comment_type should be public but found %', v_count;
    END IF;
    RAISE NOTICE 'PASS: comment_type defaults to public';
END;
$$;

\echo '-- VALID 6: verify total valid comment count'
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM ticket_comments;
    IF v_count <> 5 THEN
        RAISE EXCEPTION 'FAIL: expected 5 valid comments, found %', v_count;
    END IF;
    RAISE NOTICE 'PASS: 5 valid comment rows stored';
END;
$$;

\echo '-- VALID 7: public and internal comments have non-null authors'
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM ticket_comments
    WHERE comment_type IN ('public', 'internal')
      AND author_id IS NULL;

    IF v_count <> 0 THEN
        RAISE EXCEPTION 'FAIL: found % public/internal comments with null author', v_count;
    END IF;
    RAISE NOTICE 'PASS: all public/internal comments have authors';
END;
$$;

\echo '-- VALID 8: system comment may have null author'
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM ticket_comments
    WHERE comment_type = 'system'
      AND author_id IS NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION 'FAIL: expected 1 null-author system comment, found %', v_count;
    END IF;
    RAISE NOTICE 'PASS: system comment with null author accepted';
END;
$$;


-- =============================================================================
\echo '-- INVALID COMMENT TESTS'
-- =============================================================================

\echo '-- INVALID 1: public comment without author_id — must fail ticket_comments_author_check'
DO $$
DECLARE
    v_ticket_id UUID;
    v_constraint TEXT;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (v_ticket_id, NULL, 'No author public comment.', 'public');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for public comment without author';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint <> 'ticket_comments_author_check' THEN
                RAISE EXCEPTION 'FAIL: wrong constraint %, expected ticket_comments_author_check', v_constraint;
            END IF;
            RAISE NOTICE 'PASS: public comment without author rejected by %', v_constraint;
    END;
END;
$$;

\echo '-- INVALID 2: internal comment without author_id — must fail ticket_comments_author_check'
DO $$
DECLARE
    v_ticket_id UUID;
    v_constraint TEXT;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (v_ticket_id, NULL, 'No author internal comment.', 'internal');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for internal comment without author';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint <> 'ticket_comments_author_check' THEN
                RAISE EXCEPTION 'FAIL: wrong constraint %, expected ticket_comments_author_check', v_constraint;
            END IF;
            RAISE NOTICE 'PASS: internal comment without author rejected by %', v_constraint;
    END;
END;
$$;

\echo '-- INVALID 3: blank comment_text — must fail ticket_comments_text_not_blank_check'
DO $$
DECLARE
    v_ticket_id UUID;
    v_author_id UUID;
    v_constraint TEXT;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';
    SELECT id INTO v_author_id FROM users WHERE email = 'comment.requester@example.com';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (v_ticket_id, v_author_id, '   ', 'public');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for blank comment_text';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint <> 'ticket_comments_text_not_blank_check' THEN
                RAISE EXCEPTION 'FAIL: wrong constraint %, expected ticket_comments_text_not_blank_check', v_constraint;
            END IF;
            RAISE NOTICE 'PASS: blank comment_text rejected by %', v_constraint;
    END;
END;
$$;

\echo '-- INVALID 4: invalid comment_type "private" — must fail ticket_comments_type_check'
DO $$
DECLARE
    v_ticket_id UUID;
    v_author_id UUID;
    v_constraint TEXT;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';
    SELECT id INTO v_author_id FROM users WHERE email = 'comment.requester@example.com';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (v_ticket_id, v_author_id, 'Comment with bad type.', 'private');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for invalid comment_type "private"';
    EXCEPTION
        WHEN check_violation THEN
            GET STACKED DIAGNOSTICS v_constraint = CONSTRAINT_NAME;
            IF v_constraint <> 'ticket_comments_type_check' THEN
                RAISE EXCEPTION 'FAIL: wrong constraint %, expected ticket_comments_type_check', v_constraint;
            END IF;
            RAISE NOTICE 'PASS: invalid comment_type rejected by %', v_constraint;
    END;
END;
$$;

\echo '-- INVALID 5: comment referencing a nonexistent ticket UUID — must fail with foreign_key_violation'
DO $$
DECLARE
    v_author_id UUID;
BEGIN
    SELECT id INTO v_author_id FROM users WHERE email = 'comment.requester@example.com';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (gen_random_uuid(), v_author_id, 'Orphan comment.', 'public');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for nonexistent ticket_id';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS: nonexistent ticket_id rejected by foreign key constraint';
    END;
END;
$$;

\echo '-- INVALID 6: comment referencing a nonexistent author UUID — must fail with foreign_key_violation'
DO $$
DECLARE
    v_ticket_id UUID;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';

    BEGIN
        INSERT INTO ticket_comments (ticket_id, author_id, comment_text, comment_type)
        VALUES (v_ticket_id, gen_random_uuid(), 'Comment with fake author.', 'public');

        RAISE EXCEPTION 'FAIL: INSERT should have been rejected for nonexistent author_id';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS: nonexistent author_id rejected by foreign key constraint';
    END;
END;
$$;


-- =============================================================================
\echo '-- DELETE-PROTECTION TESTS'
-- =============================================================================

\echo '-- DELETE-PROTECT 1: delete ticket after comments exist — must fail with foreign_key_violation'
DO $$
DECLARE
    v_ticket_id UUID;
BEGIN
    SELECT id INTO v_ticket_id FROM tickets WHERE title = 'Comment test ticket';

    BEGIN
        DELETE FROM tickets WHERE id = v_ticket_id;

        RAISE EXCEPTION 'FAIL: DELETE should have been rejected because comments reference this ticket';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS: ticket delete blocked by ON DELETE RESTRICT on ticket_comments.ticket_id';
    END;
END;
$$;

\echo '-- DELETE-PROTECT 2: delete support engineer after comments exist — must fail with foreign_key_violation'
DO $$
DECLARE
    v_user_id UUID;
BEGIN
    SELECT id INTO v_user_id FROM users WHERE email = 'comment.engineer@example.com';

    BEGIN
        DELETE FROM users WHERE id = v_user_id;

        RAISE EXCEPTION 'FAIL: DELETE should have been rejected because comments reference this user';
    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE 'PASS: user delete blocked by ON DELETE RESTRICT on ticket_comments.author_id';
    END;
END;
$$;


-- =============================================================================
\echo '-- SCHEMA-SHAPE TESTS'
-- =============================================================================

\echo '-- SHAPE 1: ticket_comments table exists'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name   = 'ticket_comments'
    ) THEN
        RAISE EXCEPTION 'FAIL: table ticket_comments does not exist';
    END IF;
    RAISE NOTICE 'PASS: table ticket_comments exists';
END;
$$;

\echo '-- SHAPE 2: ticket_comments does not contain updated_at'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'ticket_comments'
          AND column_name  = 'updated_at'
    ) THEN
        RAISE EXCEPTION 'FAIL: ticket_comments must not have an updated_at column';
    END IF;
    RAISE NOTICE 'PASS: updated_at is absent from ticket_comments';
END;
$$;

\echo '-- SHAPE 3: ticket_comments does not contain deleted_at'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'ticket_comments'
          AND column_name  = 'deleted_at'
    ) THEN
        RAISE EXCEPTION 'FAIL: ticket_comments must not have a deleted_at column';
    END IF;
    RAISE NOTICE 'PASS: deleted_at is absent from ticket_comments';
END;
$$;

\echo '-- SHAPE 4: ticket_comments does not contain is_deleted'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'ticket_comments'
          AND column_name  = 'is_deleted'
    ) THEN
        RAISE EXCEPTION 'FAIL: ticket_comments must not have an is_deleted column';
    END IF;
    RAISE NOTICE 'PASS: is_deleted is absent from ticket_comments';
END;
$$;

\echo '-- SHAPE 5: composite index ticket_comments_ticket_created_idx exists'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename  = 'ticket_comments'
          AND indexname  = 'ticket_comments_ticket_created_idx'
    ) THEN
        RAISE EXCEPTION 'FAIL: index ticket_comments_ticket_created_idx does not exist';
    END IF;
    RAISE NOTICE 'PASS: index ticket_comments_ticket_created_idx exists';
END;
$$;

\echo '-- SHAPE 6: author index ticket_comments_author_id_idx exists'
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename  = 'ticket_comments'
          AND indexname  = 'ticket_comments_author_id_idx'
    ) THEN
        RAISE EXCEPTION 'FAIL: index ticket_comments_author_id_idx does not exist';
    END IF;
    RAISE NOTICE 'PASS: index ticket_comments_author_id_idx exists';
END;
$$;

\echo '-- SHAPE 7: composite index covers ticket_id, created_at, id in that order'
DO $$
DECLARE
    v_columns TEXT;
BEGIN
    SELECT string_agg(a.attname, ',' ORDER BY ix.indkey_subscript)
    INTO v_columns
    FROM pg_index         pgix
    JOIN pg_class         idx  ON idx.oid       = pgix.indexrelid
    JOIN pg_class         tbl  ON tbl.oid       = pgix.indrelid
    JOIN pg_namespace     ns   ON ns.oid        = tbl.relnamespace
    CROSS JOIN LATERAL unnest(pgix.indkey) WITH ORDINALITY AS ix(attnum, indkey_subscript)
    JOIN pg_attribute     a    ON a.attrelid    = tbl.oid
                               AND a.attnum     = ix.attnum
    WHERE ns.nspname  = 'public'
      AND tbl.relname = 'ticket_comments'
      AND idx.relname = 'ticket_comments_ticket_created_idx';

    IF v_columns IS DISTINCT FROM 'ticket_id,created_at,id' THEN
        RAISE EXCEPTION 'FAIL: composite index column order is %, expected ticket_id,created_at,id', v_columns;
    END IF;
    RAISE NOTICE 'PASS: composite index column order is ticket_id, created_at, id';
END;
$$;

\echo '-- SHAPE 8: no redundant ticket_id-only index named ticket_comments_ticket_id_idx'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename  = 'ticket_comments'
          AND indexname  = 'ticket_comments_ticket_id_idx'
    ) THEN
        RAISE EXCEPTION 'FAIL: redundant index ticket_comments_ticket_id_idx should not exist';
    END IF;
    RAISE NOTICE 'PASS: no redundant ticket_id-only index';
END;
$$;

\echo '-- SHAPE 9: foreign keys to tickets(id) and users(id) exist'
DO $$
DECLARE
    v_fk_to_tickets INTEGER;
    v_fk_to_users   INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_fk_to_tickets
    FROM information_schema.referential_constraints rc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name  = rc.constraint_name
     AND kcu.constraint_schema = rc.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name  = rc.unique_constraint_name
     AND ccu.constraint_schema = rc.unique_constraint_schema
    WHERE kcu.table_name  = 'ticket_comments'
      AND ccu.table_name  = 'tickets'
      AND ccu.column_name = 'id';

    SELECT COUNT(*) INTO v_fk_to_users
    FROM information_schema.referential_constraints rc
    JOIN information_schema.key_column_usage kcu
      ON kcu.constraint_name  = rc.constraint_name
     AND kcu.constraint_schema = rc.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name  = rc.unique_constraint_name
     AND ccu.constraint_schema = rc.unique_constraint_schema
    WHERE kcu.table_name  = 'ticket_comments'
      AND ccu.table_name  = 'users'
      AND ccu.column_name = 'id';

    IF v_fk_to_tickets < 1 THEN
        RAISE EXCEPTION 'FAIL: ticket_comments has no foreign key to tickets(id)';
    END IF;
    IF v_fk_to_users < 1 THEN
        RAISE EXCEPTION 'FAIL: ticket_comments has no foreign key to users(id)';
    END IF;
    RAISE NOTICE 'PASS: foreign keys to tickets(id) and users(id) are present';
END;
$$;


-- =============================================================================
\echo ''
\echo 'PASS: All ticket_comments schema tests completed successfully.'
-- =============================================================================
