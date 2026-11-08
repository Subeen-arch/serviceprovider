-- ---------------------------------------------------------------------------
-- Service Expert - database schema
--
-- Eleven tables describe the whole domain:
--   users                 - one row per account (customer, provider or admin)
--   services              - the service categories a customer can choose from
--   providers             - the extra details a provider needs (rate, location)
--   provider_availability - the days and hours a provider works
--   bookings              - a customer hiring a provider at a date and time
--   reviews               - a customer rating a booking they had completed
--   payments              - the Khalti payment for a booking, with its own status
--   notifications         - what to tell someone when a booking changes
--   favourite_providers   - providers a customer saved after using them
--   messages              - what someone sent us through the Contact page
--   password_reset_tokens - short-lived, single-use password recovery grants
--
-- The later domain tables are appended below so the first version stays
-- readable on its own.
--
-- Run this file with:  python setup_db.py
-- ---------------------------------------------------------------------------

-- ------------------------- users -------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(80)  NOT NULL,
    email         VARCHAR(120) NOT NULL,
    phone         VARCHAR(20)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    auth_version  INT          NOT NULL DEFAULT 0,
    role          ENUM('user', 'provider', 'admin') NOT NULL DEFAULT 'user',
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Stops two accounts sharing an email, which is what makes login reliable.
    CONSTRAINT uq_users_email UNIQUE (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- -------------------- password reset tokens -------------------------------
-- Only a SHA-256 digest is stored. Anyone who can read this table still cannot
-- use its rows as reset links, just as a password hash cannot be used to log in.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    token_hash CHAR(64)     NOT NULL,
    expires_at DATETIME     NOT NULL,
    used_at    DATETIME     NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_password_reset_token UNIQUE (token_hash),
    CONSTRAINT fk_password_reset_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    INDEX idx_password_reset_user (user_id, created_at),
    INDEX idx_password_reset_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ------------------------- services ----------------------------------------
CREATE TABLE IF NOT EXISTS services (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(60)  NOT NULL,
    icon        VARCHAR(10)  NOT NULL DEFAULT '',
    description VARCHAR(255) NOT NULL DEFAULT '',
    is_active   TINYINT(1)   NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_services_name UNIQUE (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ------------------------- providers ---------------------------------------
CREATE TABLE IF NOT EXISTS providers (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    service_id       INT NOT NULL,
    business_name    VARCHAR(100)  NOT NULL,
    bio              VARCHAR(500)  NOT NULL DEFAULT '',
    hourly_rate      DECIMAL(10,2) NOT NULL,
    experience_years INT           NOT NULL DEFAULT 0,
    address          VARCHAR(150)  NOT NULL,

    -- Where the provider works from. Used by Dijkstra and by the map markers.
    latitude         DECIMAL(10,7) NOT NULL,
    longitude        DECIMAL(10,7) NOT NULL,

    -- Set by the provider: "I am currently taking work".
    is_available     TINYINT(1) NOT NULL DEFAULT 1,
    -- Set by the admin: "this provider may appear in search results".
    is_approved      TINYINT(1) NOT NULL DEFAULT 0,

    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,

    -- One provider profile per account.
    CONSTRAINT uq_providers_user UNIQUE (user_id),
    CONSTRAINT fk_providers_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    -- RESTRICT: a service that still has providers cannot be deleted.
    CONSTRAINT fk_providers_service
        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT,

    CONSTRAINT chk_providers_rate  CHECK (hourly_rate >= 0),
    CONSTRAINT chk_providers_exp   CHECK (experience_years BETWEEN 0 AND 60),
    CONSTRAINT chk_providers_lat   CHECK (latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_providers_lng   CHECK (longitude BETWEEN -180 AND 180),

    -- Search always filters on these three columns together.
    INDEX idx_providers_search (service_id, is_approved, is_available)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ------------------------- bookings ----------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NOT NULL,
    provider_id    INT NOT NULL,
    service_id     INT NOT NULL,

    scheduled_date DATE NOT NULL,
    scheduled_time TIME NOT NULL,

    -- The job address the customer picked on the Galli map.
    address        VARCHAR(200)  NOT NULL,
    latitude       DECIMAL(10,7) NOT NULL,
    longitude      DECIMAL(10,7) NOT NULL,
    note           VARCHAR(500)  NOT NULL DEFAULT '',

    -- How long the customer expects the job to take. hourly_rate x this is the
    -- amount shown on the confirmation page and charged through Khalti.
    estimated_hours TINYINT NOT NULL DEFAULT 1,

    -- Road distance produced by the Dijkstra route, stored so the booking
    -- keeps showing the distance it was actually made with.
    distance_km    DECIMAL(6,2) NULL,

    status         ENUM('pending', 'accepted', 'rejected', 'completed', 'cancelled')
                   NOT NULL DEFAULT 'pending',

    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                             ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_bookings_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_bookings_provider
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    CONSTRAINT fk_bookings_service
        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT,

    CONSTRAINT chk_bookings_lat CHECK (latitude  BETWEEN -90  AND 90),
    CONSTRAINT chk_bookings_lng CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT chk_bookings_hours CHECK (estimated_hours BETWEEN 1 AND 12),

    INDEX idx_bookings_user     (user_id, status),
    INDEX idx_bookings_provider (provider_id, status),
    INDEX idx_bookings_slot     (provider_id, scheduled_date, scheduled_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ------------------------- reviews -----------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    booking_id  INT NOT NULL,
    user_id     INT NOT NULL,
    provider_id INT NOT NULL,
    rating      TINYINT NOT NULL,
    comment     VARCHAR(500) NOT NULL DEFAULT '',
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- The database itself guarantees one review per booking, so a double
    -- submit cannot create a second review even if two requests race.
    CONSTRAINT uq_reviews_booking UNIQUE (booking_id),
    CONSTRAINT fk_reviews_booking
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_provider
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,

    CONSTRAINT chk_reviews_rating CHECK (rating BETWEEN 1 AND 5),

    INDEX idx_reviews_provider (provider_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ------------------------- payments ----------------------------------------
-- The payment for a booking is kept in its own table and has its own status,
-- completely separate from the booking status. A booking can be pending while
-- its payment is already paid - that is the normal state while the provider
-- decides whether to accept the job.
CREATE TABLE IF NOT EXISTS payments (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    booking_id     INT NOT NULL,
    user_id        INT NOT NULL,

    amount         DECIMAL(10,2) NOT NULL,
    payment_method VARCHAR(20)   NOT NULL DEFAULT 'khalti',

    -- Khalti's own identifiers. `pidx` is the payment request, `transaction_id`
    -- is the completed transaction and only exists once the payment succeeds.
    pidx           VARCHAR(64) NULL,
    transaction_id VARCHAR(64) NULL,

    status         ENUM('pending', 'paid', 'failed', 'refunded')
                   NOT NULL DEFAULT 'pending',

    paid_at        TIMESTAMP NULL,
    refunded_at    TIMESTAMP NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- One payment record per booking.
    CONSTRAINT uq_payments_booking UNIQUE (booking_id),
    -- A Khalti payment request can never be credited to two bookings, so a
    -- replayed callback cannot pay for something it did not pay for.
    CONSTRAINT uq_payments_pidx UNIQUE (pidx),

    CONSTRAINT fk_payments_booking
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    CONSTRAINT fk_payments_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    CONSTRAINT chk_payments_amount CHECK (amount >= 0),

    INDEX idx_payments_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ===========================================================================
-- ADDED AFTER THE FIRST VERSION
--
-- Everything below is safe to run again: the tables use CREATE TABLE IF NOT
-- EXISTS, and the two ALTER statements at the very bottom are applied for you
-- by "python setup_db.py" (they are shown here so they can also be run by hand
-- in MySQL Workbench).
-- ===========================================================================


-- ------------------- provider_availability ---------------------------------
-- The working days and hours a provider accepts jobs in. One row per weekday
-- the provider actually works; a day with no row is a day off.
--
-- IMPORTANT RULE: a provider with NO rows at all is treated as available every
-- day from 06:00 to 20:00. That keeps every provider who signed up before this
-- table existed working exactly as before, instead of silently disappearing
-- from search results.
CREATE TABLE IF NOT EXISTS provider_availability (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    provider_id INT     NOT NULL,

    -- 0 = Monday, 1 = Tuesday ... 6 = Sunday (matches Python's weekday()).
    weekday     TINYINT NOT NULL,
    start_time  TIME    NOT NULL,
    end_time    TIME    NOT NULL,

    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- A provider states each working day once.
    CONSTRAINT uq_availability_day UNIQUE (provider_id, weekday),
    CONSTRAINT fk_availability_provider
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,

    CONSTRAINT chk_availability_weekday CHECK (weekday BETWEEN 0 AND 6),
    CONSTRAINT chk_availability_hours   CHECK (end_time > start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- --------------------------- notifications ---------------------------------
-- One row per thing a customer or provider should be told about. Written
-- whenever a booking changes state, and read on the bell page.
CREATE TABLE IF NOT EXISTS notifications (
    id         INT AUTO_INCREMENT PRIMARY KEY,

    -- Who should see it. This is a users.id, so the same table serves
    -- customers, providers and administrators.
    user_id    INT NOT NULL,
    -- Which booking it is about. NULL is allowed so a message that is not
    -- about a booking can still be stored later.
    booking_id INT NULL,

    message    VARCHAR(255) NOT NULL,
    is_read    TINYINT(1)   NOT NULL DEFAULT 0,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_notifications_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_notifications_booking
        FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,

    -- The bell asks "how many unread for this person" on every page.
    INDEX idx_notifications_unread (user_id, is_read, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------- database-level double-booking lock -----------------------
-- The application already refuses a clashing booking, but two requests
-- arriving at the same moment could still slip past that check. These two
-- statements make the database itself refuse it.
--
-- active_slot is a generated column: it holds "provider|date|time" while the
-- booking is live, and NULL once it is rejected, cancelled or completed.
-- MySQL allows any number of NULLs in a UNIQUE index, so a freed slot becomes
-- bookable again while a live slot can only be held once.
--
-- The column is VIRTUAL, not STORED: a stored column makes MySQL rebuild the
-- whole bookings table, which fails because payments, reviews and
-- notifications all reference it with foreign keys.
--
-- "python setup_db.py" runs these for you and skips them if they already
-- exist. To apply them by hand in Workbench, run:
--
--   ALTER TABLE bookings
--       ADD COLUMN active_slot VARCHAR(64)
--       GENERATED ALWAYS AS (
--           CASE WHEN status IN ('pending', 'accepted')
--                THEN CONCAT(provider_id, '|', scheduled_date, '|', scheduled_time)
--           END
--       ) VIRTUAL;
--
--   ALTER TABLE bookings
--       ADD CONSTRAINT uq_bookings_active_slot UNIQUE (active_slot);


-- ------------------------ favourite_providers ------------------------------
-- A customer's saved providers. A customer may only favourite a provider they
-- have actually used, which the application checks by looking for at least one
-- completed booking between them before writing a row here.
CREATE TABLE IF NOT EXISTS favourite_providers (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    provider_id INT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- The same provider can only be favourited once per customer, so pressing
    -- the heart twice can never create a duplicate row.
    CONSTRAINT uq_favourite_pair UNIQUE (user_id, provider_id),

    CONSTRAINT fk_favourite_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_favourite_provider
        FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,

    -- "show me my favourites, newest first"
    INDEX idx_favourite_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ---------------------------- messages -------------------------------------
-- Anything someone wants to tell the people running the site: a question, a
-- complaint, a bug report. Sent from the public Contact page and read by the
-- administrator.
CREATE TABLE IF NOT EXISTS messages (
    id         INT AUTO_INCREMENT PRIMARY KEY,

    -- Set when the sender was signed in, NULL when a visitor sent it while
    -- logged out. ON DELETE SET NULL rather than CASCADE: if the account is
    -- later removed the message itself must still be readable.
    user_id    INT NULL,

    name       VARCHAR(80)   NOT NULL,
    email      VARCHAR(120)  NOT NULL,
    subject    VARCHAR(120)  NOT NULL DEFAULT '',
    body       VARCHAR(2000) NOT NULL,

    is_read    TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_messages_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,

    -- The admin badge asks "how many unread" on every page.
    INDEX idx_messages_unread (is_read, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ===========================================================================
-- Added later: admin notifications and the cancellation reason
-- ---------------------------------------------------------------------------
-- These two columns are added to tables that already exist above, so they are
-- written as ALTER statements rather than being edited into the CREATE blocks.
-- setup_db.py runs them automatically and skips them if they are already
-- there; they are left here, commented out, so they can also be run by hand in
-- MySQL Workbench and read alongside the rest of the schema.
--
-- 1. notifications.title
--    Admin alerts are headed rather than being one long sentence, e.g.
--    "Provider Location Updated". The default is '' so every notification
--    written before this column existed still reads correctly.
--
-- ALTER TABLE notifications
--     ADD COLUMN title VARCHAR(120) NOT NULL DEFAULT '' AFTER booking_id;
--
-- 2. bookings.cancel_reason
--    Why the customer called the job off. Chosen in the box that appears when
--    they press Cancel, and passed on to the provider and the administrator.
--    Empty when the booking was never cancelled, or cancelled before this
--    column existed.
--
-- ALTER TABLE bookings
--     ADD COLUMN cancel_reason VARCHAR(200) NOT NULL DEFAULT '' AFTER status;
-- ===========================================================================
