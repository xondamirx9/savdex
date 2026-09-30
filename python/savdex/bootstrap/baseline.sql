--
-- PostgreSQL database dump
--






SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: activity_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_events (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    type character varying(255) NOT NULL,
    tone character varying(255) DEFAULT 'info'::character varying NOT NULL,
    message character varying(255) NOT NULL,
    url character varying(255),
    subject_type character varying(255),
    subject_id bigint,
    read_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: activity_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.activity_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: activity_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.activity_events_id_seq OWNED BY public.activity_events.id;


--
-- Name: admin_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_actions (
    id bigint NOT NULL,
    user_id bigint,
    user_name character varying(120) NOT NULL,
    user_role character varying(20),
    action character varying(40) NOT NULL,
    section character varying(40) NOT NULL,
    subject_type character varying(255),
    subject_id bigint,
    subject_label character varying(200),
    changes json,
    note text,
    ip character varying(45),
    created_at timestamp(0) without time zone NOT NULL
);


--
-- Name: admin_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admin_actions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admin_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admin_actions_id_seq OWNED BY public.admin_actions.id;


--
-- Name: audience_views; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audience_views (
    id bigint NOT NULL,
    target_company_id bigint NOT NULL,
    viewer_company_id bigint NOT NULL,
    listing_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: audience_views_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audience_views_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audience_views_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audience_views_id_seq OWNED BY public.audience_views.id;


--
-- Name: banner_images; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.banner_images (
    id bigint NOT NULL,
    banner_id bigint NOT NULL,
    locale character varying(5) NOT NULL,
    image_path character varying(255) NOT NULL,
    image_mobile_path character varying(255),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: banner_images_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.banner_images_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: banner_images_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.banner_images_id_seq OWNED BY public.banner_images.id;


--
-- Name: banners; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.banners (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    placement character varying(255) NOT NULL,
    url character varying(255),
    alt character varying(255) NOT NULL,
    image_path character varying(255) NOT NULL,
    image_mobile_path character varying(255),
    focal_x smallint DEFAULT '50'::smallint NOT NULL,
    focal_y smallint DEFAULT '50'::smallint NOT NULL,
    starts_at timestamp(0) without time zone,
    ends_at timestamp(0) without time zone,
    is_active boolean DEFAULT true NOT NULL,
    is_dismissible boolean DEFAULT true NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: banners_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.banners_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: banners_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.banners_id_seq OWNED BY public.banners.id;


--
-- Name: broadcasts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.broadcasts (
    id bigint NOT NULL,
    sent_by bigint,
    title character varying(255) NOT NULL,
    body text NOT NULL,
    url character varying(255),
    tone character varying(255) DEFAULT 'info'::character varying NOT NULL,
    audience character varying(255) DEFAULT 'all'::character varying NOT NULL,
    audience_value character varying(255),
    recipients_count integer DEFAULT 0 NOT NULL,
    sent_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: broadcasts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.broadcasts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: broadcasts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.broadcasts_id_seq OWNED BY public.broadcasts.id;


--
-- Name: cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache (
    key character varying(255) NOT NULL,
    value text NOT NULL,
    expiration bigint NOT NULL
);


--
-- Name: cache_locks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cache_locks (
    key character varying(255) NOT NULL,
    owner character varying(255) NOT NULL,
    expiration bigint NOT NULL
);


--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    id bigint NOT NULL,
    parent_id bigint,
    slug character varying(255) NOT NULL,
    icon character varying(255),
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.categories_id_seq OWNED BY public.categories.id;


--
-- Name: category_fields; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.category_fields (
    id bigint NOT NULL,
    category_id bigint NOT NULL,
    key character varying(255) NOT NULL,
    label character varying(255) NOT NULL,
    type character varying(255) DEFAULT 'select'::character varying NOT NULL,
    options json,
    unit character varying(255),
    is_required boolean DEFAULT false NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: category_fields_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.category_fields_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: category_fields_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.category_fields_id_seq OWNED BY public.category_fields.id;


--
-- Name: category_translations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.category_translations (
    id bigint NOT NULL,
    category_id bigint NOT NULL,
    locale character varying(5) NOT NULL,
    name character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: category_translations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.category_translations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: category_translations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.category_translations_id_seq OWNED BY public.category_translations.id;


--
-- Name: cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cities (
    id bigint NOT NULL,
    country_id bigint NOT NULL,
    slug character varying(255) NOT NULL,
    lat numeric(10,7),
    lng numeric(10,7),
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: cities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cities_id_seq OWNED BY public.cities.id;


--
-- Name: city_translations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_translations (
    id bigint NOT NULL,
    city_id bigint NOT NULL,
    locale character varying(5) NOT NULL,
    name character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: city_translations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.city_translations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: city_translations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.city_translations_id_seq OWNED BY public.city_translations.id;


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id bigint NOT NULL,
    slug character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    legal_name character varying(255),
    tin character varying(20),
    country_id bigint,
    city_id bigint,
    address character varying(255),
    lat numeric(10,7),
    lng numeric(10,7),
    type character varying(32),
    primary_role character varying(16) DEFAULT 'both'::character varying NOT NULL,
    description text,
    logo_path character varying(255),
    cover_path character varying(255),
    website character varying(255),
    phone character varying(32),
    email character varying(255),
    telegram character varying(64),
    whatsapp character varying(32),
    contact_person character varying(255),
    founded_year smallint,
    employees_range character varying(16),
    turnover_range character varying(16),
    verification_level smallint DEFAULT '0'::smallint NOT NULL,
    verified_at timestamp(0) without time zone,
    verified_by bigint,
    rating numeric(3,2) DEFAULT '0'::numeric NOT NULL,
    reviews_count integer DEFAULT 0 NOT NULL,
    completed_deals_count integer DEFAULT 0 NOT NULL,
    response_time_hours smallint,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    blocked_reason text,
    blocked_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    custom_category character varying(80),
    search_text text,
    source_note character varying(500),
    is_it_provider boolean DEFAULT false NOT NULL,
    it_specializations json,
    partner_tier character varying(16),
    partner_sort integer DEFAULT 0 NOT NULL,
    legal_form character varying(16) DEFAULT 'legal'::character varying NOT NULL,
    profile_changed_at timestamp(0) without time zone
);


--
-- Name: companies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.companies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.companies_id_seq OWNED BY public.companies.id;


--
-- Name: company_attributes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_attributes (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    key character varying(64) NOT NULL,
    value text,
    type character varying(16) DEFAULT 'string'::character varying NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_attributes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_attributes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_attributes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_attributes_id_seq OWNED BY public.company_attributes.id;


--
-- Name: company_category; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_category (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    category_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_category_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_category_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_category_id_seq OWNED BY public.company_category.id;


--
-- Name: company_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_contacts (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    type character varying(20) NOT NULL,
    value character varying(255) NOT NULL,
    label character varying(255),
    contact_person character varying(255),
    is_primary boolean DEFAULT false NOT NULL,
    is_public boolean DEFAULT true NOT NULL,
    sort_order smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_contacts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_contacts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_contacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_contacts_id_seq OWNED BY public.company_contacts.id;


--
-- Name: company_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_documents (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    type character varying(32) NOT NULL,
    title character varying(255) NOT NULL,
    file_path character varying(255) NOT NULL,
    file_size integer,
    mime character varying(255),
    valid_until date,
    is_public boolean DEFAULT true NOT NULL,
    moderation_status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    moderation_note text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    moderated_by bigint,
    moderated_at timestamp(0) without time zone
);


--
-- Name: company_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_documents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_documents_id_seq OWNED BY public.company_documents.id;


--
-- Name: company_invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_invitations (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    invited_by bigint NOT NULL,
    email character varying(255) NOT NULL,
    company_role character varying(16) DEFAULT 'manager'::character varying NOT NULL,
    token character varying(64) NOT NULL,
    expires_at timestamp(0) without time zone NOT NULL,
    accepted_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_invitations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_invitations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_invitations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_invitations_id_seq OWNED BY public.company_invitations.id;


--
-- Name: company_site_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_site_products (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    title character varying(190) NOT NULL,
    description text,
    price numeric(16,2),
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    unit character varying(30),
    image_path character varying(255),
    thumb_path character varying(255),
    sort integer DEFAULT 0 NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_site_products_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_site_products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_site_products_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_site_products_id_seq OWNED BY public.company_site_products.id;


--
-- Name: company_sites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_sites (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    subdomain character varying(40) NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    theme json,
    published_theme json,
    published_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_sites_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_sites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_sites_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_sites_id_seq OWNED BY public.company_sites.id;


--
-- Name: company_type_translations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_type_translations (
    id bigint NOT NULL,
    company_type_id bigint NOT NULL,
    locale character varying(5) NOT NULL,
    name character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_type_translations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_type_translations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_type_translations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_type_translations_id_seq OWNED BY public.company_type_translations.id;


--
-- Name: company_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_types (
    id bigint NOT NULL,
    code character varying(255) NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: company_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_types_id_seq OWNED BY public.company_types.id;


--
-- Name: contact_unlocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contact_unlocks (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    target_company_id bigint NOT NULL,
    user_id bigint,
    listing_id bigint,
    credits_spent smallint DEFAULT '1'::smallint NOT NULL,
    status character varying(255) DEFAULT 'new'::character varying NOT NULL,
    note text,
    complaint_status character varying(255),
    complaint_reason text,
    complained_at timestamp(0) without time zone,
    refunded boolean DEFAULT false NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    moderator_note text,
    moderated_by bigint,
    moderated_at timestamp(0) without time zone
);


--
-- Name: contact_unlocks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.contact_unlocks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: contact_unlocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.contact_unlocks_id_seq OWNED BY public.contact_unlocks.id;


--
-- Name: content_translations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_translations (
    id bigint NOT NULL,
    hash character(40) NOT NULL,
    locale character varying(8) NOT NULL,
    source text NOT NULL,
    translation text,
    attempts smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: content_translations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.content_translations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: content_translations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.content_translations_id_seq OWNED BY public.content_translations.id;


--
-- Name: countries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.countries (
    id bigint NOT NULL,
    code character varying(2) NOT NULL,
    phone_code character varying(8) NOT NULL,
    currency_code character varying(3) NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: countries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.countries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: countries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.countries_id_seq OWNED BY public.countries.id;


--
-- Name: country_translations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.country_translations (
    id bigint NOT NULL,
    country_id bigint NOT NULL,
    locale character varying(5) NOT NULL,
    name character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: country_translations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.country_translations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: country_translations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.country_translations_id_seq OWNED BY public.country_translations.id;


--
-- Name: credit_packs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_packs (
    id bigint NOT NULL,
    code character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    credits integer NOT NULL,
    price_usd numeric(10,2) NOT NULL,
    price_uzs bigint,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: credit_packs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.credit_packs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: credit_packs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.credit_packs_id_seq OWNED BY public.credit_packs.id;


--
-- Name: crm_communications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crm_communications (
    id bigint NOT NULL,
    type character varying(20) DEFAULT 'call'::character varying NOT NULL,
    happened_at timestamp(0) without time zone NOT NULL,
    summary character varying(200) NOT NULL,
    body text,
    author_id bigint,
    contact_id bigint,
    subject_type character varying(255),
    subject_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: crm_communications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.crm_communications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crm_communications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.crm_communications_id_seq OWNED BY public.crm_communications.id;


--
-- Name: crm_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crm_contacts (
    id bigint NOT NULL,
    company_id bigint,
    name character varying(160) NOT NULL,
    "position" character varying(120),
    phone character varying(40),
    email character varying(160),
    telegram character varying(80),
    note text,
    created_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: crm_contacts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.crm_contacts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crm_contacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.crm_contacts_id_seq OWNED BY public.crm_contacts.id;


--
-- Name: crm_deals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crm_deals (
    id bigint NOT NULL,
    title character varying(200) NOT NULL,
    company_id bigint,
    contact_id bigint,
    lead_id bigint,
    owner_id bigint,
    amount bigint DEFAULT '0'::bigint NOT NULL,
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    stage character varying(20) DEFAULT 'new'::character varying NOT NULL,
    expected_close_at date,
    closed_at timestamp(0) without time zone,
    lost_reason text,
    note text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: crm_deals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.crm_deals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crm_deals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.crm_deals_id_seq OWNED BY public.crm_deals.id;


--
-- Name: crm_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crm_leads (
    id bigint NOT NULL,
    title character varying(200) NOT NULL,
    source character varying(40) DEFAULT 'site'::character varying NOT NULL,
    company_id bigint,
    contact_id bigint,
    contact_name character varying(160),
    contact_phone character varying(40),
    contact_email character varying(160),
    owner_id bigint,
    status character varying(20) DEFAULT 'new'::character varying NOT NULL,
    lost_reason text,
    note text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: crm_leads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.crm_leads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crm_leads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.crm_leads_id_seq OWNED BY public.crm_leads.id;


--
-- Name: crm_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.crm_tasks (
    id bigint NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    assignee_id bigint,
    created_by bigint,
    due_at timestamp(0) without time zone,
    done_at timestamp(0) without time zone,
    subject_type character varying(255),
    subject_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: crm_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.crm_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: crm_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.crm_tasks_id_seq OWNED BY public.crm_tasks.id;


--
-- Name: exports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.exports (
    id bigint NOT NULL,
    completed_at timestamp(0) without time zone,
    file_disk character varying(255) NOT NULL,
    file_name character varying(255),
    exporter character varying(255) NOT NULL,
    processed_rows integer DEFAULT 0 NOT NULL,
    total_rows integer NOT NULL,
    successful_rows integer DEFAULT 0 NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: exports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.exports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: exports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.exports_id_seq OWNED BY public.exports.id;


--
-- Name: failed_import_rows; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failed_import_rows (
    id bigint NOT NULL,
    data json NOT NULL,
    import_id bigint NOT NULL,
    validation_error text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: failed_import_rows_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.failed_import_rows_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: failed_import_rows_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.failed_import_rows_id_seq OWNED BY public.failed_import_rows.id;


--
-- Name: failed_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.failed_jobs (
    id bigint NOT NULL,
    uuid character varying(255) NOT NULL,
    connection character varying(255) NOT NULL,
    queue character varying(255) NOT NULL,
    payload text NOT NULL,
    exception text NOT NULL,
    failed_at timestamp(0) without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.failed_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.failed_jobs_id_seq OWNED BY public.failed_jobs.id;


--
-- Name: faq_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.faq_items (
    id bigint NOT NULL,
    page_id bigint,
    question character varying(255) NOT NULL,
    answer text NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_published boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    question_i18n json,
    answer_i18n json
);


--
-- Name: faq_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.faq_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: faq_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.faq_items_id_seq OWNED BY public.faq_items.id;


--
-- Name: favorites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.favorites (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    listing_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: favorites_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.favorites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: favorites_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.favorites_id_seq OWNED BY public.favorites.id;


--
-- Name: imports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.imports (
    id bigint NOT NULL,
    completed_at timestamp(0) without time zone,
    file_name character varying(255) NOT NULL,
    file_path character varying(255) NOT NULL,
    importer character varying(255) NOT NULL,
    processed_rows integer DEFAULT 0 NOT NULL,
    total_rows integer NOT NULL,
    successful_rows integer DEFAULT 0 NOT NULL,
    user_id bigint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: imports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.imports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: imports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.imports_id_seq OWNED BY public.imports.id;


--
-- Name: it_task_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.it_task_files (
    id bigint NOT NULL,
    it_task_id bigint NOT NULL,
    title character varying(255) NOT NULL,
    file_path character varying(255) NOT NULL,
    file_size bigint DEFAULT '0'::bigint NOT NULL,
    mime character varying(255),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: it_task_files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.it_task_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: it_task_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.it_task_files_id_seq OWNED BY public.it_task_files.id;


--
-- Name: it_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.it_tasks (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    user_id bigint,
    slug character varying(255),
    title character varying(255) NOT NULL,
    description text NOT NULL,
    service_type character varying(32) NOT NULL,
    stack json,
    budget_type character varying(16) DEFAULT 'negotiable'::character varying NOT NULL,
    budget_from numeric(16,2),
    budget_to numeric(16,2),
    currency character(3) DEFAULT 'UZS'::bpchar NOT NULL,
    deadline_at date,
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    published_at timestamp(0) without time zone,
    closed_at timestamp(0) without time zone,
    responses_count integer DEFAULT 0 NOT NULL,
    views_count integer DEFAULT 0 NOT NULL,
    search_text text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    contractor_company_id bigint,
    result_url character varying(255),
    result_summary text,
    completed_at timestamp(0) without time zone
);


--
-- Name: it_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.it_tasks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: it_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.it_tasks_id_seq OWNED BY public.it_tasks.id;


--
-- Name: job_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_batches (
    id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    total_jobs integer NOT NULL,
    pending_jobs integer NOT NULL,
    failed_jobs integer NOT NULL,
    failed_job_ids text NOT NULL,
    options text,
    cancelled_at integer,
    created_at integer NOT NULL,
    finished_at integer
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id bigint NOT NULL,
    queue character varying(255) NOT NULL,
    payload text NOT NULL,
    attempts smallint NOT NULL,
    reserved_at integer,
    available_at integer NOT NULL,
    created_at integer NOT NULL
);


--
-- Name: jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.jobs_id_seq OWNED BY public.jobs.id;


--
-- Name: landing_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.landing_blocks (
    id bigint NOT NULL,
    key character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    eyebrow character varying(255),
    heading character varying(255),
    subheading text,
    payload json,
    is_visible boolean DEFAULT true NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    eyebrow_i18n json,
    heading_i18n json,
    subheading_i18n json,
    button character varying(255),
    button_i18n json,
    body text,
    body_i18n json
);


--
-- Name: landing_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.landing_blocks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: landing_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.landing_blocks_id_seq OWNED BY public.landing_blocks.id;


--
-- Name: listing_attributes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_attributes (
    id bigint NOT NULL,
    listing_id bigint NOT NULL,
    key character varying(255) NOT NULL,
    value character varying(255) NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: listing_attributes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.listing_attributes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: listing_attributes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.listing_attributes_id_seq OWNED BY public.listing_attributes.id;


--
-- Name: listing_images; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_images (
    id bigint NOT NULL,
    listing_id bigint NOT NULL,
    path character varying(255) NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    thumb_path character varying(255)
);


--
-- Name: listing_images_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.listing_images_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: listing_images_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.listing_images_id_seq OWNED BY public.listing_images.id;


--
-- Name: listing_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_stats (
    id bigint NOT NULL,
    listing_id bigint NOT NULL,
    date date NOT NULL,
    impressions integer DEFAULT 0 NOT NULL,
    views integer DEFAULT 0 NOT NULL,
    favorites integer DEFAULT 0 NOT NULL,
    unlocks integer DEFAULT 0 NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: listing_stats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.listing_stats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: listing_stats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.listing_stats_id_seq OWNED BY public.listing_stats.id;


--
-- Name: listings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listings (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    user_id bigint,
    category_id bigint,
    city_id bigint,
    type character varying(255) DEFAULT 'supply'::character varying NOT NULL,
    slug character varying(255),
    title character varying(255) NOT NULL,
    description text,
    price numeric(16,2),
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    unit character varying(255),
    price_negotiable boolean DEFAULT false NOT NULL,
    min_order integer,
    delivery_terms text,
    payment_terms text,
    status character varying(255) DEFAULT 'draft'::character varying NOT NULL,
    moderation_note text,
    wizard_step smallint DEFAULT '1'::smallint NOT NULL,
    published_at timestamp(0) without time zone,
    expires_at timestamp(0) without time zone,
    impressions_count integer DEFAULT 0 NOT NULL,
    views_count integer DEFAULT 0 NOT NULL,
    unlocks_count integer DEFAULT 0 NOT NULL,
    favorites_count integer DEFAULT 0 NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    search_text text,
    tags json,
    bundle_price numeric(14,2),
    title_i18n json,
    description_i18n json,
    source character varying(16) DEFAULT 'cabinet'::character varying NOT NULL,
    delivery_terms_i18n json,
    payment_terms_i18n json
);


--
-- Name: listings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.listings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: listings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.listings_id_seq OWNED BY public.listings.id;


--
-- Name: login_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.login_attempts (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    ip character varying(45) NOT NULL,
    successful boolean DEFAULT false NOT NULL,
    user_agent_hash character varying(64),
    created_at timestamp(0) without time zone
);


--
-- Name: login_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.login_attempts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: login_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.login_attempts_id_seq OWNED BY public.login_attempts.id;


--
-- Name: message_threads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.message_threads (
    id bigint NOT NULL,
    listing_id bigint,
    buyer_company_id bigint NOT NULL,
    seller_company_id bigint NOT NULL,
    buyer_read_at timestamp(0) without time zone,
    seller_read_at timestamp(0) without time zone,
    last_message_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    it_task_id bigint
);


--
-- Name: message_threads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.message_threads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: message_threads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.message_threads_id_seq OWNED BY public.message_threads.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id bigint NOT NULL,
    thread_id bigint NOT NULL,
    company_id bigint NOT NULL,
    user_id bigint,
    body text NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.migrations (
    id integer NOT NULL,
    migration character varying(255) NOT NULL,
    batch integer NOT NULL
);


--
-- Name: migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.migrations_id_seq OWNED BY public.migrations.id;


--
-- Name: news_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.news_posts (
    id bigint NOT NULL,
    slug character varying(255) NOT NULL,
    category character varying(255) NOT NULL,
    title character varying(255) NOT NULL,
    excerpt text NOT NULL,
    body text NOT NULL,
    image_path character varying(255),
    read_time character varying(255),
    is_published boolean DEFAULT false NOT NULL,
    published_at timestamp(0) without time zone,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    author_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    title_i18n json,
    excerpt_i18n json,
    body_i18n json
);


--
-- Name: news_posts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.news_posts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: news_posts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.news_posts_id_seq OWNED BY public.news_posts.id;


--
-- Name: notification_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_preferences (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    event character varying(255) NOT NULL,
    email boolean DEFAULT true NOT NULL,
    telegram boolean DEFAULT false NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: notification_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notification_preferences_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notification_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_preferences_id_seq OWNED BY public.notification_preferences.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    type character varying(255) NOT NULL,
    notifiable_type character varying(255) NOT NULL,
    notifiable_id bigint NOT NULL,
    data text NOT NULL,
    read_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pages (
    id bigint NOT NULL,
    key character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    title character varying(255) NOT NULL,
    excerpt text,
    body text,
    meta_title character varying(255),
    meta_description character varying(255),
    is_published boolean DEFAULT true NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    title_i18n json,
    excerpt_i18n json,
    body_i18n json
);


--
-- Name: pages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pages_id_seq OWNED BY public.pages.id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_tokens (
    email character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    created_at timestamp(0) without time zone
);


--
-- Name: payment_methods; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_methods (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    provider character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    brand character varying(255),
    last4 character varying(4) NOT NULL,
    expires character varying(5),
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: payment_methods_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payment_methods_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_methods_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payment_methods_id_seq OWNED BY public.payment_methods.id;


--
-- Name: payment_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_transactions (
    id bigint NOT NULL,
    payment_id bigint NOT NULL,
    provider character varying(255) NOT NULL,
    provider_transaction_id character varying(255),
    state character varying(255) DEFAULT 'created'::character varying NOT NULL,
    amount_minor bigint,
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    payload json,
    performed_at timestamp(0) without time zone,
    cancelled_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: payment_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payment_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payment_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payment_transactions_id_seq OWNED BY public.payment_transactions.id;


--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    payment_method_id bigint,
    subscription_id bigint,
    purpose character varying(255) NOT NULL,
    description character varying(255) NOT NULL,
    amount bigint NOT NULL,
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    provider character varying(255),
    external_id character varying(255),
    status character varying(255) DEFAULT 'pending'::character varying NOT NULL,
    paid_at timestamp(0) without time zone,
    invoice_path character varying(255),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    number character varying(20),
    plan_id bigint,
    credit_pack_id bigint,
    confirmed_by bigint,
    admin_note text,
    promo_code_id bigint
);


--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.payments_id_seq OWNED BY public.payments.id;


--
-- Name: plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plans (
    id bigint NOT NULL,
    code character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    price_usd numeric(10,2) DEFAULT '0'::numeric NOT NULL,
    price_uzs bigint,
    period_days smallint DEFAULT '30'::smallint NOT NULL,
    listings_limit integer,
    contacts_limit integer,
    promo_units integer DEFAULT 0 NOT NULL,
    verification_days smallint DEFAULT '5'::smallint NOT NULL,
    advanced_analytics boolean DEFAULT false NOT NULL,
    sees_interested_names boolean DEFAULT false NOT NULL,
    has_microsite boolean DEFAULT false NOT NULL,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    listing_days smallint DEFAULT '30'::smallint NOT NULL,
    responses_limit integer
);


--
-- Name: plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.plans_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.plans_id_seq OWNED BY public.plans.id;


--
-- Name: platform_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_reviews (
    id bigint NOT NULL,
    user_id bigint,
    company_id bigint,
    rating smallint NOT NULL,
    rating_usability smallint,
    rating_search smallint,
    rating_support smallint,
    body text NOT NULL,
    status character varying(20) DEFAULT 'moderation'::character varying NOT NULL,
    screening_flags character varying(255),
    moderator_note text,
    moderated_by bigint,
    moderated_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: platform_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: platform_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_reviews_id_seq OWNED BY public.platform_reviews.id;


--
-- Name: promo_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promo_codes (
    id bigint NOT NULL,
    code character varying(32) NOT NULL,
    plan_id bigint NOT NULL,
    days smallint NOT NULL,
    expires_at timestamp(0) without time zone,
    is_active boolean DEFAULT true NOT NULL,
    note character varying(255),
    used_at timestamp(0) without time zone,
    used_by_company_id bigint,
    used_by_user_id bigint,
    subscription_id bigint,
    created_by bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    discount_percent smallint
);


--
-- Name: promo_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.promo_codes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: promo_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.promo_codes_id_seq OWNED BY public.promo_codes.id;


--
-- Name: promotion_types; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promotion_types (
    id bigint NOT NULL,
    code character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(255) NOT NULL,
    effect_hint character varying(255),
    cost_units smallint NOT NULL,
    duration_days smallint DEFAULT '0'::smallint NOT NULL,
    slots smallint,
    badge character varying(255),
    icon character varying(255),
    sort smallint DEFAULT '0'::smallint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: promotion_types_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.promotion_types_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: promotion_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.promotion_types_id_seq OWNED BY public.promotion_types.id;


--
-- Name: promotions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.promotions (
    id bigint NOT NULL,
    listing_id bigint NOT NULL,
    company_id bigint NOT NULL,
    promotion_type_id bigint NOT NULL,
    category_id bigint,
    units_spent smallint NOT NULL,
    status character varying(255) DEFAULT 'active'::character varying NOT NULL,
    starts_at timestamp(0) without time zone NOT NULL,
    ends_at timestamp(0) without time zone,
    impressions_before integer DEFAULT 0 NOT NULL,
    impressions_after integer,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    active_key character varying(64)
);


--
-- Name: promotions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.promotions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: promotions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.promotions_id_seq OWNED BY public.promotions.id;


--
-- Name: refunds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.refunds (
    id bigint NOT NULL,
    payment_id bigint NOT NULL,
    company_id bigint,
    amount bigint NOT NULL,
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    reason text NOT NULL,
    status character varying(20) DEFAULT 'requested'::character varying NOT NULL,
    created_by bigint,
    decided_by bigint,
    decided_at timestamp(0) without time zone,
    decision_note text,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: refunds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.refunds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: refunds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.refunds_id_seq OWNED BY public.refunds.id;


--
-- Name: resumes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resumes (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    slug character varying(255),
    title character varying(120) NOT NULL,
    field character varying(40),
    country_id bigint,
    city_id bigint,
    salary integer,
    currency character varying(3) DEFAULT 'UZS'::character varying NOT NULL,
    employment json,
    schedule json,
    experience_months smallint DEFAULT '0'::smallint NOT NULL,
    about text,
    skills json,
    jobs json,
    education json,
    languages json,
    photo_path character varying(255),
    contact_name character varying(255),
    contact_phone character varying(32),
    contact_email character varying(255),
    show_phone boolean DEFAULT true NOT NULL,
    show_email boolean DEFAULT true NOT NULL,
    status character varying(16) DEFAULT 'draft'::character varying NOT NULL,
    moderation_note character varying(255),
    published_at timestamp(0) without time zone,
    views_count integer DEFAULT 0 NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone,
    title_i18n json,
    about_i18n json,
    jobs_i18n json
);


--
-- Name: resumes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resumes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resumes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resumes_id_seq OWNED BY public.resumes.id;


--
-- Name: reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reviews (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    author_company_id bigint NOT NULL,
    author_user_id bigint,
    contact_unlock_id bigint,
    listing_id bigint,
    rating smallint NOT NULL,
    rating_description smallint,
    rating_response smallint,
    rating_deadlines smallint,
    rating_quality smallint,
    body text NOT NULL,
    deal_confirmed boolean DEFAULT false NOT NULL,
    reply text,
    replied_at timestamp(0) without time zone,
    dispute_status character varying(255),
    dispute_reason text,
    status character varying(255) DEFAULT 'published'::character varying NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    moderator_note text,
    moderated_by bigint,
    moderated_at timestamp(0) without time zone,
    screening_flags character varying(255),
    origin character varying(255) DEFAULT 'buyer'::character varying NOT NULL,
    created_by bigint
);


--
-- Name: reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reviews_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reviews_id_seq OWNED BY public.reviews.id;


--
-- Name: search_hits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_hits (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    query character varying(255) NOT NULL,
    date date NOT NULL,
    impressions integer DEFAULT 0 NOT NULL,
    clicks integer DEFAULT 0 NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: search_hits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.search_hits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: search_hits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.search_hits_id_seq OWNED BY public.search_hits.id;


--
-- Name: sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sessions (
    id character varying(255) NOT NULL,
    user_id bigint,
    ip_address character varying(45),
    user_agent text,
    payload text NOT NULL,
    last_activity integer NOT NULL
);


--
-- Name: settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.settings (
    id bigint NOT NULL,
    "group" character varying(40) DEFAULT 'general'::character varying NOT NULL,
    key character varying(255) NOT NULL,
    label character varying(255) NOT NULL,
    description text,
    type character varying(20) DEFAULT 'string'::character varying NOT NULL,
    value json,
    sort smallint DEFAULT '0'::smallint NOT NULL,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.settings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.settings_id_seq OWNED BY public.settings.id;


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subscriptions (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    status character varying(255) DEFAULT 'active'::character varying NOT NULL,
    started_at timestamp(0) without time zone NOT NULL,
    ends_at timestamp(0) without time zone,
    auto_renew boolean DEFAULT true NOT NULL,
    cancelled_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    source character varying(255) DEFAULT 'payment'::character varying NOT NULL,
    granted_by bigint,
    grant_reason character varying(255)
);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subscriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: support_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_messages (
    id bigint NOT NULL,
    ticket_id bigint NOT NULL,
    author_id bigint,
    from_staff boolean DEFAULT false NOT NULL,
    is_internal boolean DEFAULT false NOT NULL,
    body text NOT NULL,
    attachments json,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: support_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.support_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: support_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.support_messages_id_seq OWNED BY public.support_messages.id;


--
-- Name: support_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_tickets (
    id bigint NOT NULL,
    subject character varying(200) NOT NULL,
    user_id bigint,
    company_id bigint,
    author_name character varying(160),
    author_email character varying(160),
    assignee_id bigint,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    channel character varying(20) DEFAULT 'form'::character varying NOT NULL,
    priority character varying(10) DEFAULT 'normal'::character varying NOT NULL,
    last_reply_at timestamp(0) without time zone,
    closed_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    deleted_at timestamp(0) without time zone
);


--
-- Name: support_tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.support_tickets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: support_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.support_tickets_id_seq OWNED BY public.support_tickets.id;


--
-- Name: tenders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenders (
    id bigint NOT NULL,
    slug character varying(255),
    title character varying(255) NOT NULL,
    title_i18n json,
    description text,
    description_i18n json,
    customer character varying(255),
    category_id bigint,
    country_id bigint,
    location character varying(255),
    budget numeric(16,2),
    currency character(3) DEFAULT 'UZS'::bpchar NOT NULL,
    deadline_at timestamp(0) without time zone,
    source_url character varying(255),
    contact_name character varying(255),
    contact_phone character varying(40),
    contact_email character varying(255),
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    published_at timestamp(0) without time zone,
    views_count integer DEFAULT 0 NOT NULL,
    search_text text,
    author_id bigint,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    is_government boolean DEFAULT false NOT NULL
);


--
-- Name: tenders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tenders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tenders_id_seq OWNED BY public.tenders.id;


--
-- Name: user_notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_notifications (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    company_id bigint,
    type character varying(255) NOT NULL,
    tone character varying(255) DEFAULT 'info'::character varying NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    url character varying(255),
    subject_type character varying(255),
    subject_id bigint,
    sent_by bigint,
    is_broadcast boolean DEFAULT false NOT NULL,
    read_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: user_notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_notifications_id_seq OWNED BY public.user_notifications.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    email_verified_at timestamp(0) without time zone,
    password character varying(255) NOT NULL,
    remember_token character varying(100),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    company_id bigint,
    phone character varying(32),
    phone_verified_at timestamp(0) without time zone,
    locale character varying(5) DEFAULT 'ru'::character varying NOT NULL,
    company_role character varying(16) DEFAULT 'owner'::character varying NOT NULL,
    is_admin boolean DEFAULT false NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    two_factor_secret character varying(255),
    two_factor_confirmed_at timestamp(0) without time zone,
    last_login_at timestamp(0) without time zone,
    last_login_ip character varying(45),
    status character varying(16) DEFAULT 'active'::character varying NOT NULL,
    deleted_at timestamp(0) without time zone,
    admin_role character varying(20),
    admin_permissions json,
    telegram_chat_id character varying(32),
    telegram_username character varying(64),
    telegram_linked_at timestamp(0) without time zone,
    account_type character varying(16) DEFAULT 'legal'::character varying NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: wallet_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallet_transactions (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    user_id bigint,
    kind character varying(255) NOT NULL,
    amount integer NOT NULL,
    balance_after integer NOT NULL,
    reason character varying(255) NOT NULL,
    subject_type character varying(255),
    subject_id bigint,
    comment character varying(255),
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone
);


--
-- Name: wallet_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wallet_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wallet_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wallet_transactions_id_seq OWNED BY public.wallet_transactions.id;


--
-- Name: wallets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wallets (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    credits integer DEFAULT 0 NOT NULL,
    promo_units integer DEFAULT 0 NOT NULL,
    contacts_used_this_period integer DEFAULT 0 NOT NULL,
    period_resets_at timestamp(0) without time zone,
    created_at timestamp(0) without time zone,
    updated_at timestamp(0) without time zone,
    responses_used_this_period integer DEFAULT 0 NOT NULL
);


--
-- Name: wallets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wallets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wallets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wallets_id_seq OWNED BY public.wallets.id;


--
-- Name: activity_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_events ALTER COLUMN id SET DEFAULT nextval('public.activity_events_id_seq'::regclass);


--
-- Name: admin_actions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions ALTER COLUMN id SET DEFAULT nextval('public.admin_actions_id_seq'::regclass);


--
-- Name: audience_views id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audience_views ALTER COLUMN id SET DEFAULT nextval('public.audience_views_id_seq'::regclass);


--
-- Name: banner_images id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banner_images ALTER COLUMN id SET DEFAULT nextval('public.banner_images_id_seq'::regclass);


--
-- Name: banners id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banners ALTER COLUMN id SET DEFAULT nextval('public.banners_id_seq'::regclass);


--
-- Name: broadcasts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts ALTER COLUMN id SET DEFAULT nextval('public.broadcasts_id_seq'::regclass);


--
-- Name: categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories ALTER COLUMN id SET DEFAULT nextval('public.categories_id_seq'::regclass);


--
-- Name: category_fields id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_fields ALTER COLUMN id SET DEFAULT nextval('public.category_fields_id_seq'::regclass);


--
-- Name: category_translations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_translations ALTER COLUMN id SET DEFAULT nextval('public.category_translations_id_seq'::regclass);


--
-- Name: cities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities ALTER COLUMN id SET DEFAULT nextval('public.cities_id_seq'::regclass);


--
-- Name: city_translations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_translations ALTER COLUMN id SET DEFAULT nextval('public.city_translations_id_seq'::regclass);


--
-- Name: companies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies ALTER COLUMN id SET DEFAULT nextval('public.companies_id_seq'::regclass);


--
-- Name: company_attributes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_attributes ALTER COLUMN id SET DEFAULT nextval('public.company_attributes_id_seq'::regclass);


--
-- Name: company_category id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_category ALTER COLUMN id SET DEFAULT nextval('public.company_category_id_seq'::regclass);


--
-- Name: company_contacts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts ALTER COLUMN id SET DEFAULT nextval('public.company_contacts_id_seq'::regclass);


--
-- Name: company_documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_documents ALTER COLUMN id SET DEFAULT nextval('public.company_documents_id_seq'::regclass);


--
-- Name: company_invitations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations ALTER COLUMN id SET DEFAULT nextval('public.company_invitations_id_seq'::regclass);


--
-- Name: company_site_products id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_site_products ALTER COLUMN id SET DEFAULT nextval('public.company_site_products_id_seq'::regclass);


--
-- Name: company_sites id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_sites ALTER COLUMN id SET DEFAULT nextval('public.company_sites_id_seq'::regclass);


--
-- Name: company_type_translations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_type_translations ALTER COLUMN id SET DEFAULT nextval('public.company_type_translations_id_seq'::regclass);


--
-- Name: company_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_types ALTER COLUMN id SET DEFAULT nextval('public.company_types_id_seq'::regclass);


--
-- Name: contact_unlocks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks ALTER COLUMN id SET DEFAULT nextval('public.contact_unlocks_id_seq'::regclass);


--
-- Name: content_translations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_translations ALTER COLUMN id SET DEFAULT nextval('public.content_translations_id_seq'::regclass);


--
-- Name: countries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countries ALTER COLUMN id SET DEFAULT nextval('public.countries_id_seq'::regclass);


--
-- Name: country_translations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.country_translations ALTER COLUMN id SET DEFAULT nextval('public.country_translations_id_seq'::regclass);


--
-- Name: credit_packs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_packs ALTER COLUMN id SET DEFAULT nextval('public.credit_packs_id_seq'::regclass);


--
-- Name: crm_communications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_communications ALTER COLUMN id SET DEFAULT nextval('public.crm_communications_id_seq'::regclass);


--
-- Name: crm_contacts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_contacts ALTER COLUMN id SET DEFAULT nextval('public.crm_contacts_id_seq'::regclass);


--
-- Name: crm_deals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals ALTER COLUMN id SET DEFAULT nextval('public.crm_deals_id_seq'::regclass);


--
-- Name: crm_leads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_leads ALTER COLUMN id SET DEFAULT nextval('public.crm_leads_id_seq'::regclass);


--
-- Name: crm_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_tasks ALTER COLUMN id SET DEFAULT nextval('public.crm_tasks_id_seq'::regclass);


--
-- Name: exports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exports ALTER COLUMN id SET DEFAULT nextval('public.exports_id_seq'::regclass);


--
-- Name: failed_import_rows id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_import_rows ALTER COLUMN id SET DEFAULT nextval('public.failed_import_rows_id_seq'::regclass);


--
-- Name: failed_jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs ALTER COLUMN id SET DEFAULT nextval('public.failed_jobs_id_seq'::regclass);


--
-- Name: faq_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faq_items ALTER COLUMN id SET DEFAULT nextval('public.faq_items_id_seq'::regclass);


--
-- Name: favorites id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites ALTER COLUMN id SET DEFAULT nextval('public.favorites_id_seq'::regclass);


--
-- Name: imports id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imports ALTER COLUMN id SET DEFAULT nextval('public.imports_id_seq'::regclass);


--
-- Name: it_task_files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_task_files ALTER COLUMN id SET DEFAULT nextval('public.it_task_files_id_seq'::regclass);


--
-- Name: it_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks ALTER COLUMN id SET DEFAULT nextval('public.it_tasks_id_seq'::regclass);


--
-- Name: jobs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs ALTER COLUMN id SET DEFAULT nextval('public.jobs_id_seq'::regclass);


--
-- Name: landing_blocks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.landing_blocks ALTER COLUMN id SET DEFAULT nextval('public.landing_blocks_id_seq'::regclass);


--
-- Name: listing_attributes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_attributes ALTER COLUMN id SET DEFAULT nextval('public.listing_attributes_id_seq'::regclass);


--
-- Name: listing_images id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_images ALTER COLUMN id SET DEFAULT nextval('public.listing_images_id_seq'::regclass);


--
-- Name: listing_stats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_stats ALTER COLUMN id SET DEFAULT nextval('public.listing_stats_id_seq'::regclass);


--
-- Name: listings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings ALTER COLUMN id SET DEFAULT nextval('public.listings_id_seq'::regclass);


--
-- Name: login_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts ALTER COLUMN id SET DEFAULT nextval('public.login_attempts_id_seq'::regclass);


--
-- Name: message_threads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads ALTER COLUMN id SET DEFAULT nextval('public.message_threads_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations ALTER COLUMN id SET DEFAULT nextval('public.migrations_id_seq'::regclass);


--
-- Name: news_posts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_posts ALTER COLUMN id SET DEFAULT nextval('public.news_posts_id_seq'::regclass);


--
-- Name: notification_preferences id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_preferences ALTER COLUMN id SET DEFAULT nextval('public.notification_preferences_id_seq'::regclass);


--
-- Name: pages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages ALTER COLUMN id SET DEFAULT nextval('public.pages_id_seq'::regclass);


--
-- Name: payment_methods id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_methods ALTER COLUMN id SET DEFAULT nextval('public.payment_methods_id_seq'::regclass);


--
-- Name: payment_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions ALTER COLUMN id SET DEFAULT nextval('public.payment_transactions_id_seq'::regclass);


--
-- Name: payments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments ALTER COLUMN id SET DEFAULT nextval('public.payments_id_seq'::regclass);


--
-- Name: plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plans ALTER COLUMN id SET DEFAULT nextval('public.plans_id_seq'::regclass);


--
-- Name: platform_reviews id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews ALTER COLUMN id SET DEFAULT nextval('public.platform_reviews_id_seq'::regclass);


--
-- Name: promo_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes ALTER COLUMN id SET DEFAULT nextval('public.promo_codes_id_seq'::regclass);


--
-- Name: promotion_types id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotion_types ALTER COLUMN id SET DEFAULT nextval('public.promotion_types_id_seq'::regclass);


--
-- Name: promotions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions ALTER COLUMN id SET DEFAULT nextval('public.promotions_id_seq'::regclass);


--
-- Name: refunds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds ALTER COLUMN id SET DEFAULT nextval('public.refunds_id_seq'::regclass);


--
-- Name: resumes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes ALTER COLUMN id SET DEFAULT nextval('public.resumes_id_seq'::regclass);


--
-- Name: reviews id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews ALTER COLUMN id SET DEFAULT nextval('public.reviews_id_seq'::regclass);


--
-- Name: search_hits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_hits ALTER COLUMN id SET DEFAULT nextval('public.search_hits_id_seq'::regclass);


--
-- Name: settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings ALTER COLUMN id SET DEFAULT nextval('public.settings_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: support_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_messages ALTER COLUMN id SET DEFAULT nextval('public.support_messages_id_seq'::regclass);


--
-- Name: support_tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets ALTER COLUMN id SET DEFAULT nextval('public.support_tickets_id_seq'::regclass);


--
-- Name: tenders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders ALTER COLUMN id SET DEFAULT nextval('public.tenders_id_seq'::regclass);


--
-- Name: user_notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notifications ALTER COLUMN id SET DEFAULT nextval('public.user_notifications_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: wallet_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions ALTER COLUMN id SET DEFAULT nextval('public.wallet_transactions_id_seq'::regclass);


--
-- Name: wallets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets ALTER COLUMN id SET DEFAULT nextval('public.wallets_id_seq'::regclass);


--
-- Data for Name: activity_events; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: admin_actions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: audience_views; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: banner_images; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: banners; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: broadcasts; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: cache; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: cache_locks; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: category_fields; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: category_translations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: cities; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: city_translations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: companies; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_attributes; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_category; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_contacts; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_documents; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_invitations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_site_products; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_sites; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: company_type_translations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.company_type_translations VALUES (1, 1, 'ru', 'Производитель', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (2, 1, 'uz', 'Ishlab chiqaruvchi', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (3, 1, 'en', 'Manufacturer', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (4, 1, 'zh', '制造商', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (5, 1, 'tr', 'Üretici', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (6, 2, 'ru', 'Импортёр', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (7, 2, 'uz', 'Importchi', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (8, 2, 'en', 'Importer', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (9, 2, 'zh', '进口商', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (10, 2, 'tr', 'İthalatçı', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (11, 3, 'ru', 'Дистрибьютор', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (12, 3, 'uz', 'Distribyutor', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (13, 3, 'en', 'Distributor', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (14, 3, 'zh', '经销商', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (15, 3, 'tr', 'Distribütör', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (16, 4, 'ru', 'Торговая компания', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (17, 4, 'uz', 'Savdo kompaniyasi', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (18, 4, 'en', 'Trading company', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (19, 4, 'zh', '贸易公司', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (20, 4, 'tr', 'Ticaret şirketi', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (21, 5, 'ru', 'Услуги', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (22, 5, 'uz', 'Xizmatlar', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (23, 5, 'en', 'Services', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (24, 5, 'zh', '服务', '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_type_translations VALUES (25, 5, 'tr', 'Hizmetler', '2026-09-30 16:00:41', '2026-09-30 16:00:41');


--
-- Data for Name: company_types; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.company_types VALUES (1, 'manufacturer', 0, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_types VALUES (2, 'importer', 1, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_types VALUES (3, 'distributor', 2, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_types VALUES (4, 'trader', 3, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.company_types VALUES (5, 'service', 4, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');


--
-- Data for Name: contact_unlocks; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: content_translations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: countries; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: country_translations; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: credit_packs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.credit_packs VALUES (1, 'pack_10', '10 контактов', 10, 9.00, NULL, 1, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.credit_packs VALUES (2, 'pack_30', '30 контактов', 30, 24.00, NULL, 2, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.credit_packs VALUES (3, 'pack_100', '100 контактов', 100, 69.00, NULL, 3, true, '2026-09-30 16:00:41', '2026-09-30 16:00:41');


--
-- Data for Name: crm_communications; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: crm_contacts; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: crm_deals; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: crm_leads; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: crm_tasks; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: exports; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: failed_import_rows; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: failed_jobs; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: faq_items; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.faq_items VALUES (1, 3, 'Сколько стоит разместить объявление?', 'Размещение бесплатно на всех тарифах. Бесплатный тариф даёт 4 активных объявления и 3 раскрытия контактов в месяц.', 0, true, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"E’lon joylashtirish qancha turadi?","en":"How much does posting a listing cost?","zh":"发布一条信息要多少钱？","tr":"İlan yayımlamak ne kadar tutuyor?"}', '{"uz":"Joylashtirish barcha tariflarda bepul. Bepul tarif oyiga 4 ta faol e’lon va 3 marta kontakt ochish imkonini beradi.","en":"Posting is free on every plan. The free plan gives 4 active listings and 3 contact unlocks per month.","zh":"所有套餐均可免费发布。免费套餐每月提供 4 条有效信息和 3 次联系方式解锁。","tr":"Yayımlamak tüm tarifelerde ücretsizdir. Ücretsiz tarife ayda 4 aktif ilan ve 3 iletişim açma hakkı verir."}');
INSERT INTO public.faq_items VALUES (2, 3, 'Почему контакты платные?', 'Мы не берём процент со сделок, поэтому доступ к контактам — единственный источник дохода площадки. Открыв контакт компании один раз, вы видите его навсегда по всем её объявлениям.', 1, true, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Nega kontaktlar pullik?","en":"Why are contacts paid?","zh":"为什么联系方式要付费？","tr":"İletişim bilgileri neden ücretli?"}', '{"uz":"Biz bitimlardan foiz olmaymiz, shuning uchun kontaktlarga kirish — maydonning yagona daromad manbai. Kompaniya kontaktini bir marta ochsangiz, uning barcha e’lonlarida umrbod ko‘rinadi.","en":"We take no percentage of deals, so access to contacts is the platform’s only source of income. Unlock a company’s contact once and you keep it for good, across all of its listings.","zh":"我们不抽取交易佣金，因此解锁联系方式是平台唯一的收入来源。解锁某家企业的联系方式后，其全部信息中都将长期可见。","tr":"İşlemlerden pay almıyoruz, bu yüzden iletişim bilgilerine erişim platformun tek gelir kaynağıdır. Bir şirketin iletişim bilgisini bir kez açtığınızda, onun tüm ilanlarında kalıcı olarak görürsünüz."}');
INSERT INTO public.faq_items VALUES (3, 3, 'Что делать, если контакт нерабочий?', 'Нажмите «Пожаловаться на контакт» в разделе «Мои контакты». Проверим за 2 рабочих дня; при подтверждении вернём кредит и снизим компании индекс отзывчивости.', 2, true, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Kontakt ishlamasa nima qilish kerak?","en":"What if a contact does not work?","zh":"联系方式无法接通怎么办？","tr":"İletişim bilgisi çalışmıyorsa ne yapmalı?"}', '{"uz":"«Mening kontaktlarim» bo‘limida «Kontakt haqida shikoyat» tugmasini bosing. 2 ish kunida tekshiramiz; tasdiqlansa, kreditni qaytaramiz va kompaniyaning javob berish ko‘rsatkichini pasaytiramiz.","en":"Press “Report contact” in the “My contacts” section. We check within 2 business days; if confirmed, we return the credit and lower the company’s responsiveness score.","zh":"在「我的联系方式」中点击「举报联系方式」。我们将在 2 个工作日内核查；情况属实将退回额度，并下调该企业的响应评分。","tr":"«İletişim bilgilerim» bölümünde «İletişimi bildir» düğmesine basın. 2 iş günü içinde kontrol ederiz; doğrulanırsa krediyi iade eder ve şirketin yanıt verme puanını düşürürüz."}');
INSERT INTO public.faq_items VALUES (4, 3, 'Как получить бейдж «Проверена»?', 'Загрузите свидетельство о регистрации и подтвердите ИНН. Модератор проверит: на Free и Flash — до 5 рабочих дней, на Business и Premium — 1 рабочий день. Бейдж не продаётся.', 3, true, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"«Tekshirilgan» belgisini qanday olish mumkin?","en":"How do I get the “Verified” badge?","zh":"如何获得「已核验」标识？","tr":"«Doğrulanmış» rozeti nasıl alınır?"}', '{"uz":"Ro‘yxatdan o‘tish guvohnomasini yuklang va STIRni tasdiqlang. Moderator tekshiradi: Free va Flash tariflarida 5 ish kunigacha, Business va Premiumda 1 ish kuni. Belgi sotilmaydi.","en":"Upload the certificate of registration and confirm the tax ID. A moderator checks it: up to 5 business days on Free and Flash, 1 business day on Business and Premium. The badge is not for sale.","zh":"上传注册证书并确认税号。审核员会进行核查：Free 与 Flash 套餐最长 5 个工作日，Business 与 Premium 为 1 个工作日。该标识不出售。","tr":"Kayıt belgesini yükleyin ve vergi numarasını doğrulayın. Moderatör kontrol eder: Free ve Flash’ta 5 iş gününe kadar, Business ve Premium’da 1 iş günü. Rozet satılık değildir."}');
INSERT INTO public.faq_items VALUES (5, 3, 'Какими картами можно оплатить?', 'Картами Uzcard, Humo, Visa и Mastercard через интернет-эквайринг Uzum Bank, в сумах. Платёж подтверждается кодом 3-D Secure. Подробнее — на странице «Способы оплаты».', 4, true, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Qaysi kartalar bilan to‘lash mumkin?","en":"Which cards can I pay with?","zh":"可以用哪些银行卡支付？","tr":"Hangi kartlarla ödeme yapılabilir?"}', '{"uz":"Uzcard, Humo, Visa va Mastercard kartalari bilan Uzum Bank internet-ekvayringi orqali, so‘mda. To‘lov 3-D Secure kodi bilan tasdiqlanadi. Batafsil — «To‘lov usullari» sahifasida.","en":"Uzcard, Humo, Visa and Mastercard through Uzum Bank online acquiring, in soum. The payment is confirmed by a 3-D Secure code. Details are on the “Payment methods” page.","zh":"可使用 Uzcard、Humo、Visa 和 Mastercard，通过 Uzum Bank 网络收单以苏姆支付。付款需经 3-D Secure 验证码确认。详见「支付方式」页面。","tr":"Uzcard, Humo, Visa ve Mastercard ile Uzum Bank internet sanal POS üzerinden, som cinsinden. Ödeme 3-D Secure koduyla onaylanır. Ayrıntılar «Ödeme yöntemleri» sayfasında."}');


--
-- Data for Name: favorites; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: imports; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: it_task_files; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: it_tasks; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: job_batches; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: jobs; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: landing_blocks; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.landing_blocks VALUES (1, 'hero', 'Первый экран', NULL, 'Поставщики и закупщики находят друг друга', 'Разместите предложение или запрос бесплатно. Получите прямые контакты компаний — без посредников и без комиссии со сделок.', NULL, true, 0, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Yetkazib beruvchilar va xaridorlar bir-birini topadi","en":"Where suppliers and buyers find each other","zh":"供应商与采购商在此相遇","tr":"Tedarikçiler ve alıcılar burada buluşuyor"}', '{"uz":"Taklif yoki so‘rovni bepul joylashtiring. Kompaniyalarning to‘g‘ridan-to‘g‘ri kontaktlarini oling — vositachilarsiz va bitimdan komissiyasiz.","en":"Post an offer or a request for free. Get direct company contacts — no middlemen, no commission on deals.","zh":"免费发布供应或求购信息，直接获取企业联系方式 —— 没有中间商，交易不收佣金。","tr":"Teklifinizi veya talebinizi ücretsiz yayınlayın. Şirketlerin doğrudan iletişim bilgilerini alın — aracısız ve işlem komisyonu olmadan."}', NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (2, 'stats', 'Счётчики', NULL, NULL, NULL, NULL, true, 1, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (3, 'categories', 'Популярные категории', NULL, 'Популярные категории', NULL, NULL, true, 2, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Ommabop toifalar","en":"Popular categories","zh":"热门类目","tr":"Popüler kategoriler"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (4, 'vip', 'VIP-предложения', NULL, 'VIP-предложения', NULL, NULL, true, 3, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"VIP takliflar","en":"VIP offers","zh":"VIP 精选","tr":"VIP teklifler"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (5, 'requests', 'Запросы', NULL, 'Запросы', NULL, NULL, true, 4, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"So‘rovlar","en":"Requests","zh":"采购需求","tr":"Talepler"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (6, 'suppliers', 'Поставщики', NULL, 'Поставщики', NULL, NULL, true, 5, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Yetkazib beruvchilar","en":"Suppliers","zh":"供应商","tr":"Tedarikçiler"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (7, 'how', 'Как это работает', 'Как это работает', 'Четыре шага до прямого разговора', 'От регистрации до сделки — без посредников и согласований.', NULL, true, 6, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Bu qanday ishlaydi","en":"How it works","zh":"如何运作","tr":"Nasıl çalışır"}', '{"uz":"To‘g‘ridan-to‘g‘ri suhbatgacha to‘rt qadam","en":"Four steps to a direct conversation","zh":"四步直接对话","tr":"Doğrudan görüşmeye dört adım"}', '{"uz":"Ro‘yxatdan o‘tishdan bitimgacha — vositachilarsiz va kelishuvlarsiz.","en":"From sign-up to the deal — no middlemen, no approvals.","zh":"从注册到成交 —— 没有中间商，无需层层审批。","tr":"Kayıttan anlaşmaya — aracısız ve onay beklemeden."}', NULL, NULL, 'Зарегистрируйтесь
Почта, пароль, данные компании. Две минуты, карта не нужна.

Разместите товар
Категория, объём, цена, условия поставки, фото и сертификаты.

Получайте входящие
Видно, кто открыл ваши контакты, из какого города и по какому объявлению.

Договоритесь напрямую
Созвон, договор, оплата — всё между вами. Площадка не вмешивается.', '{"uz":"Ro‘yxatdan o‘ting\nPochta, parol, kompaniya ma’lumotlari. Ikki daqiqa, karta kerak emas.\n\nMahsulotni joylashtiring\nToifa, hajm, narx, yetkazib berish shartlari, foto va sertifikatlar.\n\nKiruvchi so‘rovlarni oling\nKontaktlaringizni kim, qaysi shahardan va qaysi e’lon bo‘yicha ochgani ko‘rinadi.\n\nTo‘g‘ridan-to‘g‘ri kelishing\nQo‘ng‘iroq, shartnoma, to‘lov — barchasi o‘zingiz o‘rtangizda. Platforma aralashmaydi.","en":"Sign up\nEmail, password, company details. Two minutes, no card required.\n\nPost your goods\nCategory, volume, price, delivery terms, photos and certificates.\n\nReceive enquiries\nYou see who unlocked your contacts, from which city and for which listing.\n\nAgree directly\nCalls, contracts, payments — all between you. The platform stays out of it.","zh":"注册账号\n邮箱、密码、企业资料。两分钟，无需银行卡。\n\n发布货源\n类目、数量、价格、供货条件、照片与证书。\n\n接收询盘\n可以看到谁解锁了您的联系方式、来自哪个城市、针对哪条信息。\n\n直接洽谈\n通话、合同、付款 —— 全在双方之间，平台不介入。","tr":"Kayıt olun\nE-posta, şifre, şirket bilgileri. İki dakika, kart gerekmez.\n\nÜrününüzü yayınlayın\nKategori, miktar, fiyat, teslim koşulları, fotoğraf ve sertifikalar.\n\nTalepleri alın\nİletişim bilgilerinizi kimin, hangi şehirden ve hangi ilan için açtığı görünür.\n\nDoğrudan anlaşın\nGörüşme, sözleşme, ödeme — hepsi aranızda. Platform araya girmez."}');
INSERT INTO public.landing_blocks VALUES (8, 'reviews', 'Отзывы', NULL, 'Отзывы пользователей', NULL, NULL, true, 7, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Foydalanuvchilar fikrlari","en":"User reviews","zh":"用户评价","tr":"Kullanıcı yorumları"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (9, 'faq', 'Частые вопросы', NULL, 'Частые вопросы', NULL, NULL, true, 8, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Ko‘p beriladigan savollar","en":"Frequently asked questions","zh":"常见问题","tr":"Sık sorulan sorular"}', NULL, NULL, NULL, 'Сколько стоит размещение объявлений?
Размещение бесплатное. Платные тарифы расширяют лимиты — больше объявлений, контактов и продвижения, — но базовая работа на площадке не стоит ничего.

Берёте ли вы комиссию со сделок?
Нет. Сделка проходит напрямую между вами и партнёром: созвон, договор, оплата. Площадка в расчётах не участвует и процента не берёт.

Как проверяются компании?
Модерация сверяет учредительные документы и ИНН. Прошедшие проверку получают бейдж «Проверена», расширенная проверка — «Проверена+». Отзывы появляются только от компаний, открывших контакты через площадку, — накрутить их нельзя.

Как связаться с поставщиком?
Откройте визитку компании и нажмите «Открыть контакты». На бесплатном тарифе — 3 открытия контактов в месяц, на платных лимит выше. Открытый контакт остаётся у вас навсегда.

Кто может зарегистрироваться на площадке?
Компании и предприниматели Узбекистана и всего региона: производители, импортёры, дистрибьюторы, торговые компании и сервисы. Нужны только почта и данные компании.

На каких языках работает площадка?
Русский, узбекский, английский, турецкий и китайский. Язык переключается в шапке сайта, и ссылку на страницу можно отправить партнёру сразу на его языке.', '{"uz":"E’lon joylashtirish qancha turadi?\nJoylashtirish bepul. Pullik tariflar limitlarni kengaytiradi — ko‘proq e’lon, kontakt va ilgari surish, — ammo maydondagi asosiy ish hech qancha turmaydi.\n\nBitimlardan komissiya olasizmi?\nYo‘q. Bitim siz va hamkoringiz o‘rtasida to‘g‘ridan-to‘g‘ri o‘tadi: qo‘ng‘iroq, shartnoma, to‘lov. Maydon hisob-kitoblarda qatnashmaydi va foiz olmaydi.\n\nKompaniyalar qanday tekshiriladi?\nModeratsiya ta’sis hujjatlari va STIRni tekshiradi. Tekshiruvdan o‘tganlar «Tekshirilgan» belgisini oladi, kengaytirilgan tekshiruv — «Tekshirilgan+». Sharhlarni faqat platforma orqali kontaktlarni ochgan kompaniyalar qoldira oladi — reytingni sun’iy oshirib bo‘lmaydi.\n\nYetkazib beruvchi bilan qanday bog‘lansa bo‘ladi?\nKompaniya sahifasini oching va «Kontaktlarni ochish» tugmasini bosing. Bepul tarifda oyiga 3 ta ochish bor, pullik tariflarda ko‘proq. Ochilgan kontakt sizda abadiy qoladi.\n\nMaydonda kim ro‘yxatdan o‘ta oladi?\nO‘zbekiston va butun mintaqa kompaniyalari hamda tadbirkorlari: ishlab chiqaruvchilar, importchilar, distribyutorlar, savdo kompaniyalari va xizmatlar. Faqat pochta va kompaniya ma’lumotlari kerak.\n\nMaydon qaysi tillarda ishlaydi?\nRus, o‘zbek, ingliz, turk va xitoy tillarida. Til sayt sarlavhasida almashtiriladi, sahifa havolasini hamkorga o‘z tilida yuborish mumkin.","en":"How much does posting cost?\nPosting is free. Paid plans extend the limits — more listings, contacts and promotion — but basic work on the platform costs nothing.\n\nDo you take a commission on deals?\nNo. The deal happens directly between you and your partner: call, contract, payment. The platform is not involved in settlements and takes no percentage.\n\nHow are companies verified?\nModerators verify incorporation documents and the TIN. Verified companies get the “Verified” badge; extended checks earn “Verified+”. Reviews can only be left by companies that unlocked contacts through the platform, so ratings cannot be faked.\n\nHow do I contact a supplier?\nOpen a company profile and click “Unlock contacts”. The free plan includes 3 contact unlocks per month; paid plans include more. An unlocked contact stays with you forever.\n\nWho can register on the platform?\nCompanies and entrepreneurs from Uzbekistan and the whole region: manufacturers, importers, distributors, trading companies and services. You only need an email and company details.\n\nWhich languages does the platform support?\nRussian, Uzbek, English, Turkish and Chinese. Switch the language in the site header and share page links with partners in their own language.","zh":"发布信息需要多少费用？\n发布免费。付费套餐扩大限额——更多信息、联系方式和推广——但平台的基本使用不收任何费用。\n\n你们从交易中抽取佣金吗？\n不。交易在您与伙伴之间直接进行：通话、合同、付款。平台不参与结算，也不抽取任何比例。\n\n公司是如何审核的？\n审核人员核对公司注册文件和税号。通过审核的企业获得“已认证”标识，扩展审核获得“已认证+”。只有通过平台解锁联系方式的企业才能留下评价，评分无法造假。\n\n如何联系供应商？\n打开企业名片并点击“解锁联系方式”。免费套餐每月含 3 次解锁，付费套餐更多。解锁的联系方式永久保留。\n\n谁可以在平台注册？\n乌兹别克斯坦及整个地区的公司和企业家：制造商、进口商、经销商、贸易公司和服务商。只需邮箱和公司信息。\n\n平台支持哪些语言？\n俄语、乌兹别克语、英语、土耳其语和中文。语言可在网站顶部切换，页面链接可直接以伙伴的语言发送给对方。","tr":"İlan yayınlamak ne kadar?\nYayınlamak ücretsizdir. Ücretli paketler limitleri genişletir — daha fazla ilan, iletişim ve tanıtım — ancak platformdaki temel çalışma hiçbir şey tutmaz.\n\nAnlaşmalardan komisyon alıyor musunuz?\nHayır. Anlaşma sizinle ortağınız arasında doğrudan yapılır: görüşme, sözleşme, ödeme. Platform hesaplaşmalara karışmaz ve yüzde almaz.\n\nŞirketler nasıl doğrulanıyor?\nModerasyon kuruluş belgelerini ve vergi numarasını kontrol eder. Onaylananlar «Doğrulanmış» rozetini, genişletilmiş kontrol «Doğrulanmış+» rozetini alır. Yorumları yalnızca platform üzerinden iletişim bilgilerini açan şirketler bırakabilir — puan şişirilemez.\n\nTedarikçiyle nasıl iletişim kurarım?\nŞirket sayfasını açın ve «İletişimi aç» düğmesine basın. Ücretsiz pakette ayda 3 açma hakkı vardır, ücretli paketlerde daha fazla. Açılan iletişim bilgisi sonsuza dek sizde kalır.\n\nPlatforma kimler kaydolabilir?\nÖzbekistan ve tüm bölgeden şirketler ve girişimciler: üreticiler, ithalatçılar, distribütörler, ticaret şirketleri ve hizmetler. Yalnızca e-posta ve şirket bilgileri gerekir.\n\nPlatform hangi dillerde çalışıyor?\nRusça, Özbekçe, İngilizce, Türkçe ve Çince. Dil, site üstbilgisinden değiştirilir; sayfa bağlantısını ortağınıza kendi dilinde gönderebilirsiniz."}');
INSERT INTO public.landing_blocks VALUES (10, 'news', 'Новости', 'Блог', 'Новости площадки', NULL, NULL, true, 9, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Blog","en":"Blog","zh":"博客","tr":"Blog"}', '{"uz":"Platforma yangiliklari","en":"Platform news","zh":"平台动态","tr":"Platform haberleri"}', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.landing_blocks VALUES (11, 'cta', 'Призыв в конце', NULL, 'Разместите первое объявление бесплатно', 'Регистрация занимает две минуты. Карта не нужна.', NULL, true, 10, '2026-09-30 16:00:42', '2026-09-30 16:00:42', NULL, '{"uz":"Birinchi e’loningizni bepul joylashtiring","en":"Post your first listing for free","zh":"免费发布您的第一条信息","tr":"İlk ilanınızı ücretsiz yayınlayın"}', '{"uz":"Ro‘yxatdan o‘tish ikki daqiqa oladi. Karta kerak emas.","en":"Signing up takes two minutes. No card required.","zh":"注册只需两分钟，无需银行卡。","tr":"Kayıt iki dakika sürer. Kart gerekmez."}', 'Зарегистрироваться', '{"uz":"Ro‘yxatdan o‘tish","en":"Sign up","zh":"注册","tr":"Kayıt ol"}', 'Бесплатно · 4 объявления · 3 контакта в месяц · без привязки карты', '{"uz":"Bepul · 4 ta e’lon · oyiga 3 ta kontakt · kartani bog‘lamasdan","en":"Free · 4 listings · 3 contacts a month · no card required","zh":"免费 · 4 条信息 · 每月 3 个联系方式 · 无需绑卡","tr":"Ücretsiz · 4 ilan · ayda 3 iletişim · kart bağlamadan"}');


--
-- Data for Name: listing_attributes; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: listing_images; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: listing_stats; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: listings; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: login_attempts; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: message_threads; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.migrations VALUES (1, '0001_01_01_000000_create_users_table', 1);
INSERT INTO public.migrations VALUES (2, '0001_01_01_000001_create_cache_table', 1);
INSERT INTO public.migrations VALUES (3, '0001_01_01_000002_create_jobs_table', 1);
INSERT INTO public.migrations VALUES (4, '2026_07_28_100000_create_countries_and_cities_tables', 1);
INSERT INTO public.migrations VALUES (5, '2026_07_28_100100_create_companies_table', 1);
INSERT INTO public.migrations VALUES (6, '2026_07_28_100200_extend_users_table', 1);
INSERT INTO public.migrations VALUES (7, '2026_07_28_100300_create_company_contacts_table', 1);
INSERT INTO public.migrations VALUES (8, '2026_07_28_100400_create_categories_table', 1);
INSERT INTO public.migrations VALUES (9, '2026_07_28_100500_create_plans_and_subscriptions_table', 1);
INSERT INTO public.migrations VALUES (10, '2026_07_28_100600_create_listings_table', 1);
INSERT INTO public.migrations VALUES (11, '2026_07_28_100700_create_contact_unlocks_table', 1);
INSERT INTO public.migrations VALUES (12, '2026_07_28_100800_create_reviews_table', 1);
INSERT INTO public.migrations VALUES (13, '2026_07_28_100900_create_promotions_table', 1);
INSERT INTO public.migrations VALUES (14, '2026_07_28_101000_create_payments_table', 1);
INSERT INTO public.migrations VALUES (15, '2026_07_28_101100_create_activity_and_notifications_table', 1);
INSERT INTO public.migrations VALUES (16, '2026_07_29_070147_create_imports_table', 1);
INSERT INTO public.migrations VALUES (17, '2026_07_29_070148_create_exports_table', 1);
INSERT INTO public.migrations VALUES (18, '2026_07_29_070149_create_failed_import_rows_table', 1);
INSERT INTO public.migrations VALUES (19, '2026_07_29_100000_create_notifications_table', 1);
INSERT INTO public.migrations VALUES (20, '2026_07_29_100100_create_company_category_table', 1);
INSERT INTO public.migrations VALUES (21, '2026_07_29_100200_add_admin_role_to_users_table', 1);
INSERT INTO public.migrations VALUES (22, '2026_07_29_100300_create_cms_tables', 1);
INSERT INTO public.migrations VALUES (23, '2026_07_29_100400_create_notifications_table_laravel', 1);
INSERT INTO public.migrations VALUES (24, '2026_07_29_100500_add_listing_days_to_plans_table', 1);
INSERT INTO public.migrations VALUES (25, '2026_07_29_100600_add_search_text_to_listings_table', 1);
INSERT INTO public.migrations VALUES (26, '2026_07_29_100700_create_company_types_table', 1);
INSERT INTO public.migrations VALUES (27, '2026_07_29_101200_add_manual_grant_to_subscriptions_table', 1);
INSERT INTO public.migrations VALUES (28, '2026_07_29_102000_normalize_country_codes', 1);
INSERT INTO public.migrations VALUES (29, '2026_07_29_110000_add_active_promotion_guard', 1);
INSERT INTO public.migrations VALUES (30, '2026_07_29_120000_add_moderation_trail', 1);
INSERT INTO public.migrations VALUES (31, '2026_07_29_130000_create_credit_packs_and_orders', 1);
INSERT INTO public.migrations VALUES (32, '2026_07_29_140000_add_review_screening_flags', 1);
INSERT INTO public.migrations VALUES (33, '2026_07_29_150000_add_listing_image_thumbs', 1);
INSERT INTO public.migrations VALUES (34, '2026_07_29_160000_backfill_payment_numbers', 1);
INSERT INTO public.migrations VALUES (35, '2026_08_13_120000_create_payment_transactions_table', 1);
INSERT INTO public.migrations VALUES (36, '2026_08_17_000000_add_office_location_settings', 1);
INSERT INTO public.migrations VALUES (37, '2026_08_18_000000_add_responses_limit_to_plans_table', 1);
INSERT INTO public.migrations VALUES (38, '2026_08_20_000000_sync_legal_requisites_with_offer', 1);
INSERT INTO public.migrations VALUES (39, '2026_08_20_100000_create_promo_codes_table', 1);
INSERT INTO public.migrations VALUES (40, '2026_08_20_200000_add_hero_image_setting', 1);
INSERT INTO public.migrations VALUES (41, '2026_08_23_100000_add_discount_promo_codes', 1);
INSERT INTO public.migrations VALUES (42, '2026_08_24_110000_create_message_threads', 1);
INSERT INTO public.migrations VALUES (43, '2026_08_26_100000_add_custom_category_to_companies', 1);
INSERT INTO public.migrations VALUES (44, '2026_08_28_120000_widen_company_documents_mime', 1);
INSERT INTO public.migrations VALUES (45, '2026_08_28_130000_create_audience_views', 1);
INSERT INTO public.migrations VALUES (46, '2026_08_29_100000_activate_pending_listings', 1);
INSERT INTO public.migrations VALUES (47, '2026_08_30_100000_add_tags_to_listings', 1);
INSERT INTO public.migrations VALUES (48, '2026_08_30_110000_add_bundle_price_to_listings', 1);
INSERT INTO public.migrations VALUES (49, '2026_08_30_120000_normalize_imported_company_names', 1);
INSERT INTO public.migrations VALUES (50, '2026_08_30_160000_honest_showcase_cleanup', 1);
INSERT INTO public.migrations VALUES (51, '2026_08_30_170000_reindex_search_text_for_transliteration', 1);
INSERT INTO public.migrations VALUES (52, '2026_08_30_170500_add_search_text_to_companies', 1);
INSERT INTO public.migrations VALUES (53, '2026_08_30_190000_restore_hero_image_setting', 1);
INSERT INTO public.migrations VALUES (54, '2026_08_31_100000_add_listing_translations', 1);
INSERT INTO public.migrations VALUES (55, '2026_08_31_110000_add_company_source_note', 1);
INSERT INTO public.migrations VALUES (56, '2026_08_31_120000_shorten_source_note', 1);
INSERT INTO public.migrations VALUES (57, '2026_09_05_100000_create_tenders_table', 1);
INSERT INTO public.migrations VALUES (58, '2026_09_12_100000_create_it_tasks_tables', 1);
INSERT INTO public.migrations VALUES (59, '2026_09_12_110000_add_result_to_it_tasks', 1);
INSERT INTO public.migrations VALUES (60, '2026_09_14_120000_add_admin_permissions_to_users_table', 1);
INSERT INTO public.migrations VALUES (61, '2026_09_15_100000_create_admin_actions_table', 1);
INSERT INTO public.migrations VALUES (62, '2026_09_15_110000_create_crm_tables', 1);
INSERT INTO public.migrations VALUES (63, '2026_09_15_120000_create_support_tickets_table', 1);
INSERT INTO public.migrations VALUES (64, '2026_09_15_130000_create_refunds_table', 1);
INSERT INTO public.migrations VALUES (65, '2026_09_15_140000_add_translations_to_news_posts', 1);
INSERT INTO public.migrations VALUES (66, '2026_09_15_150000_add_logo_setting', 1);
INSERT INTO public.migrations VALUES (67, '2026_09_16_100000_add_listing_source_and_terms_translations', 1);
INSERT INTO public.migrations VALUES (68, '2026_09_16_110000_add_display_currency_settings', 1);
INSERT INTO public.migrations VALUES (69, '2026_09_18_090000_add_telegram_link_to_users', 1);
INSERT INTO public.migrations VALUES (70, '2026_09_18_100000_create_resumes_table', 1);
INSERT INTO public.migrations VALUES (71, '2026_09_18_110000_add_translations_to_resumes', 1);
INSERT INTO public.migrations VALUES (72, '2026_09_18_120000_create_banners_tables', 1);
INSERT INTO public.migrations VALUES (73, '2026_09_18_130000_add_origin_to_reviews', 1);
INSERT INTO public.migrations VALUES (74, '2026_09_18_150000_unique_company_wide_review', 1);
INSERT INTO public.migrations VALUES (75, '2026_09_26_120000_fix_banner_times_entered_as_utc', 1);
INSERT INTO public.migrations VALUES (76, '2026_09_26_140000_create_company_sites_table', 1);
INSERT INTO public.migrations VALUES (77, '2026_09_27_100000_create_company_site_products_table', 1);
INSERT INTO public.migrations VALUES (78, '2026_09_27_120000_grant_django_countries', 1);
INSERT INTO public.migrations VALUES (79, '2026_09_27_140000_grant_django_cities', 1);
INSERT INTO public.migrations VALUES (80, '2026_09_27_160000_grant_django_company_types', 1);
INSERT INTO public.migrations VALUES (81, '2026_09_27_180000_create_content_translations_table', 1);
INSERT INTO public.migrations VALUES (82, '2026_09_27_180000_grant_django_categories', 1);
INSERT INTO public.migrations VALUES (83, '2026_09_27_200000_grant_django_credit_packs', 1);
INSERT INTO public.migrations VALUES (84, '2026_09_27_220000_grant_django_settings', 1);
INSERT INTO public.migrations VALUES (85, '2026_09_28_100000_add_partner_tier_to_companies', 1);
INSERT INTO public.migrations VALUES (86, '2026_09_28_100000_grant_django_banners', 1);
INSERT INTO public.migrations VALUES (87, '2026_09_28_120000_add_legal_form', 1);
INSERT INTO public.migrations VALUES (88, '2026_09_28_120000_grant_django_news', 1);
INSERT INTO public.migrations VALUES (89, '2026_09_28_140000_grant_django_plans', 1);
INSERT INTO public.migrations VALUES (90, '2026_09_28_160000_pages_from_dictionaries', 1);
INSERT INTO public.migrations VALUES (91, '2026_09_28_160100_grant_django_pages', 1);
INSERT INTO public.migrations VALUES (92, '2026_09_28_180000_landing_from_dictionaries', 1);
INSERT INTO public.migrations VALUES (93, '2026_09_28_180100_grant_django_landing', 1);
INSERT INTO public.migrations VALUES (94, '2026_09_28_200000_grant_django_content_translations', 1);
INSERT INTO public.migrations VALUES (95, '2026_09_29_100000_create_platform_reviews_table', 1);
INSERT INTO public.migrations VALUES (96, '2026_09_29_100000_lowercase_user_emails', 1);
INSERT INTO public.migrations VALUES (97, '2026_09_29_110000_hide_demo_seeded_reviews', 1);
INSERT INTO public.migrations VALUES (98, '2026_09_29_120000_hide_demo_data', 1);
INSERT INTO public.migrations VALUES (99, '2026_09_29_130000_remove_showcase_fill', 1);
INSERT INTO public.migrations VALUES (100, '2026_09_30_100000_grant_django_view_counters', 1);
INSERT INTO public.migrations VALUES (101, '2026_09_30_110000_grant_django_audience_views', 1);
INSERT INTO public.migrations VALUES (102, '2026_09_30_120000_grant_django_catalog_stats', 1);
INSERT INTO public.migrations VALUES (103, '2026_09_30_130000_grant_django_listing_views', 1);
INSERT INTO public.migrations VALUES (104, '2026_09_30_140000_drop_rfq_from_requests_block', 1);
INSERT INTO public.migrations VALUES (105, '2026_10_01_100000_grant_django_sessions', 1);
INSERT INTO public.migrations VALUES (106, '2026_10_01_110000_grant_django_chat_read', 1);
INSERT INTO public.migrations VALUES (107, '2026_10_01_120000_grant_django_first_forms', 1);
INSERT INTO public.migrations VALUES (108, '2026_10_01_130000_grant_django_translations', 1);
INSERT INTO public.migrations VALUES (109, '2026_10_01_140000_add_is_government_to_tenders', 1);
INSERT INTO public.migrations VALUES (110, '2026_10_01_150000_grant_django_listing_actions', 1);
INSERT INTO public.migrations VALUES (111, '2026_10_01_160000_grant_django_contact_actions', 1);
INSERT INTO public.migrations VALUES (112, '2026_10_01_170000_grant_django_review_actions', 1);
INSERT INTO public.migrations VALUES (113, '2026_10_01_180000_grant_django_chat_actions', 1);
INSERT INTO public.migrations VALUES (114, '2026_10_01_190000_grant_django_it_task_actions', 1);
INSERT INTO public.migrations VALUES (115, '2026_10_01_200000_grant_django_resume_actions', 1);
INSERT INTO public.migrations VALUES (116, '2026_10_01_210000_grant_django_settings_profile', 1);
INSERT INTO public.migrations VALUES (117, '2026_10_01_220000_grant_django_company_contacts', 1);
INSERT INTO public.migrations VALUES (118, '2026_10_01_230000_grant_django_resume_update', 1);
INSERT INTO public.migrations VALUES (119, '2026_10_01_240000_grant_django_company_profile', 1);
INSERT INTO public.migrations VALUES (120, '2026_10_02_100000_add_profile_changed_at_to_companies_table', 1);
INSERT INTO public.migrations VALUES (121, '2026_10_02_100000_grant_django_company_sites', 1);
INSERT INTO public.migrations VALUES (122, '2026_10_02_110000_grant_django_listing_images', 1);
INSERT INTO public.migrations VALUES (123, '2026_10_02_120000_grant_django_listing_wizard', 1);
INSERT INTO public.migrations VALUES (124, '2026_10_02_130000_grant_django_contact_unlock', 1);
INSERT INTO public.migrations VALUES (125, '2026_10_02_140000_grant_django_company_review', 1);
INSERT INTO public.migrations VALUES (126, '2026_10_02_150000_grant_django_company_files', 1);
INSERT INTO public.migrations VALUES (127, '2026_10_02_160000_grant_django_it_task_form', 1);
INSERT INTO public.migrations VALUES (128, '2026_10_02_170000_grant_django_promo_photo', 1);
INSERT INTO public.migrations VALUES (129, '2026_10_02_180000_grant_django_auth', 1);
INSERT INTO public.migrations VALUES (130, '2026_10_02_190000_grant_django_onboarding', 1);
INSERT INTO public.migrations VALUES (131, '2026_10_02_200000_grant_django_company_info', 1);
INSERT INTO public.migrations VALUES (132, '2026_10_03_100000_free_email_of_deleted_users', 1);
INSERT INTO public.migrations VALUES (133, '2026_10_03_110000_grant_django_users_admin', 1);
INSERT INTO public.migrations VALUES (134, '2026_10_04_100000_grant_django_crm_contacts', 1);
INSERT INTO public.migrations VALUES (135, '2026_10_04_110000_grant_django_crm_leads_deals', 1);
INSERT INTO public.migrations VALUES (136, '2026_10_04_120000_grant_django_crm_tasks_communications', 1);
INSERT INTO public.migrations VALUES (137, '2026_10_04_130000_grant_django_support', 1);
INSERT INTO public.migrations VALUES (138, '2026_10_04_140000_grant_django_moderation', 1);
INSERT INTO public.migrations VALUES (139, '2026_10_04_150000_grant_django_admin_sections', 1);
INSERT INTO public.migrations VALUES (140, '2026_10_09_100000_grant_django_billing_forms', 1);
INSERT INTO public.migrations VALUES (141, '2026_10_09_110000_grant_django_billing_orders', 1);
INSERT INTO public.migrations VALUES (142, '2026_10_09_120000_grant_django_payment_callbacks', 1);
INSERT INTO public.migrations VALUES (143, '2026_10_10_100000_grant_django_finance_admin', 1);
INSERT INTO public.migrations VALUES (144, '2026_10_10_110000_grant_django_refunds', 1);
INSERT INTO public.migrations VALUES (145, '2026_10_10_120000_grant_django_complaints', 1);
INSERT INTO public.migrations VALUES (146, '2026_10_11_100000_grant_django_catalog_owner', 1);
INSERT INTO public.migrations VALUES (147, '2026_10_11_110000_grant_django_cabinet_owner', 1);
INSERT INTO public.migrations VALUES (148, '2026_10_11_120000_grant_django_companies_owner', 1);
INSERT INTO public.migrations VALUES (149, '2026_10_11_130000_grant_django_user_notifications_owner', 1);
INSERT INTO public.migrations VALUES (150, '2026_10_12_100000_grant_django_users_and_money_owner', 1);


--
-- Data for Name: news_posts; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: notification_preferences; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: pages; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.pages VALUES (1, 'about', 'about', 'О компании', 'SAVDEX — площадка, на которой поставщики и закупщики находят друг друга напрямую.', 'Мы работаем в Узбекистане и Центральной Азии. Компании публикуют, что могут поставить или что хотят купить, находят партнёра и договариваются между собой. Площадка не участвует в переговорах, не берёт процент со сделки и не проводит через себя деньги.

Зарабатываем мы на подписке и доступе к контактам. Наш доход не зависит от суммы вашего контракта.', NULL, NULL, true, 0, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Kompaniya haqida","en":"About the company","zh":"关于公司","tr":"Şirket hakkında"}', '{"uz":"SAVDEX — yetkazib beruvchilar va xaridorlar bir-birini to‘g‘ridan-to‘g‘ri topadigan maydon.","en":"SAVDEX is a marketplace where suppliers and buyers find each other directly.","zh":"SAVDEX 是供应商与采购商直接找到彼此的平台。","tr":"SAVDEX, tedarikçiler ile alıcıların birbirini doğrudan bulduğu bir platformdur."}', '{"uz":"Biz O‘zbekiston va Markaziy Osiyoda ishlaymiz. Kompaniyalar nimani yetkazib bera olishini yoki nimani sotib olmoqchi ekanini e’lon qiladi, hamkor topadi va o‘zaro kelishadi. Maydon muzokaralarda qatnashmaydi, bitimdan foiz olmaydi va pulni o‘zi orqali o‘tkazmaydi.\n\nBiz obuna va kontaktlarga kirishdan daromad olamiz. Daromadimiz shartnomangiz summasiga bog‘liq emas.","en":"We work in Uzbekistan and Central Asia. Companies publish what they can supply or what they want to buy, find a partner and agree between themselves. The platform takes no part in the talks, takes no percentage of the deal and never handles the money.\n\nWe earn from subscriptions and access to contacts. Our income does not depend on the size of your contract.","zh":"我们在乌兹别克斯坦和中亚开展业务。企业发布自己能供应什么或想采购什么，找到伙伴并自行商谈。平台不参与谈判，不抽取交易佣金，也不经手资金。\n\n我们的收入来自订阅和联系方式的解锁，与您的合同金额无关。","tr":"Özbekistan ve Orta Asya’da çalışıyoruz. Şirketler ne tedarik edebileceğini ya da ne almak istediğini yayımlar, ortağını bulur ve kendi aralarında anlaşır. Platform görüşmelere katılmaz, işlemden pay almaz ve parayı kendi üzerinden geçirmez.\n\nGelirimiz abonelik ve iletişim bilgilerine erişimden gelir. Kazancımız sözleşmenizin tutarına bağlı değildir."}');
INSERT INTO public.pages VALUES (2, 'contacts', 'contacts', 'Контакты', NULL, 'Приезжайте, если вопрос проще решить лично. Договоры и документы принимаем и по почте — приезжать ради подписи необязательно.', NULL, NULL, true, 1, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Aloqa","en":"Contacts","zh":"联系方式","tr":"İletişim"}', NULL, '{"uz":"Savolni shaxsan hal qilish osonroq bo‘lsa, kelavering. Shartnoma va hujjatlarni pochta orqali ham qabul qilamiz — imzo uchun kelish shart emas.","en":"Come over if a question is easier to settle in person. We also accept contracts and documents by post — there is no need to travel just for a signature.","zh":"如果当面解决更方便，欢迎来访。合同和文件也可以邮寄办理 — 不必仅为签字专程前来。","tr":"Konuyu yüz yüze çözmek daha kolaysa buyurun gelin. Sözleşme ve belgeleri posta ile de alıyoruz — yalnızca imza için yola çıkmak gerekmez."}');
INSERT INTO public.pages VALUES (3, 'help', 'help', 'Помощь', 'Ответы на вопросы, которые задают чаще всего. Не нашли свой — напишите в поддержку.', NULL, NULL, NULL, true, 2, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Yordam","en":"Help","zh":"帮助","tr":"Yardım"}', '{"uz":"Eng ko‘p beriladigan savollarga javoblar. O‘z savolingizni topmadingizmi — qo‘llab-quvvatlash xizmatiga yozing.","en":"Answers to the questions we hear most often. Didn’t find yours? Write to support.","zh":"最常见问题的解答。没有找到您的问题？请联系客服。","tr":"En sık sorulan soruların yanıtları. Sorunuzu bulamadıysanız destek ekibine yazın."}', NULL);
INSERT INTO public.pages VALUES (4, 'guide', 'guide', 'Инструкция использования', 'Как начать работать с площадкой — поставщику и закупщику.', '## Если вы поставщик

1. Зарегистрируйтесь и подтвердите почту.
До подтверждения кабинет доступен, но публиковать нельзя.
2. Заполните карточку компании.
Заполненный профиль получает втрое больше обращений.
3. Разместите объявление.
Укажите точную марку и объём — по ним ищут. Объявления с ценой смотрят в 2,4 раза чаще.
4. Следите за входящими.
Видно, какая компания открыла ваши контакты и по какому объявлению.

## Если вы закупщик

1. Найдите в каталоге или опубликуйте запрос.
Каталог виден целиком без оплаты.
2. Изучите компанию до звонка.
Документы, рейтинг, отзывы, срок на площадке — всё открыто.
3. Откройте контакт.
Кредит списывается за компанию, а не за объявление.', NULL, NULL, true, 3, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Foydalanish qo‘llanmasi","en":"How to use the platform","zh":"使用指南","tr":"Kullanım kılavuzu"}', '{"uz":"Platformada ishni qanday boshlash kerak — yetkazib beruvchi va xaridor uchun.","en":"How to get started on the platform — for suppliers and buyers.","zh":"如何开始使用平台——供应商与采购方指南。","tr":"Platformda nasıl başlanır — tedarikçiler ve alıcılar için."}', '{"uz":"## Agar siz yetkazib beruvchi bo‘lsangiz\n\n1. Ro‘yxatdan o‘ting va pochtani tasdiqlang.\nTasdiqlanmaguncha kabinet ochiq, lekin e’lon joylashtirib bo‘lmaydi.\n2. Kompaniya kartasini to‘ldiring.\nTo‘ldirilgan profil uch barobar ko‘p murojaat oladi.\n3. E’lon joylashtiring.\nAniq marka va hajmni ko‘rsating — qidiruv shular bo‘yicha boradi. Narxi ko‘rsatilgan e’lonlar 2,4 barobar ko‘p ochiladi.\n4. Kiruvchi murojaatlarni kuzating.\nQaysi kompaniya kontaktlaringizni va qaysi e’lon bo‘yicha ochgani ko‘rinadi.\n\n## Agar siz xaridor bo‘lsangiz\n\n1. Katalogdan toping yoki so‘rov joylashtiring.\nKatalog to‘liq, to‘lovsiz ko‘rinadi.\n2. Qo‘ng‘iroqdan oldin kompaniyani o‘rganing.\nHujjatlar, reyting, sharhlar, maydondagi muddat — hammasi ochiq.\n3. Kontaktni oching.\nKredit e’lon uchun emas, kompaniya uchun yechiladi.","en":"## If you are a supplier\n\n1. Sign up and confirm your email.\nThe dashboard works before confirmation, but publishing does not.\n2. Fill in your company profile.\nA complete profile gets three times more enquiries.\n3. Post a listing.\nGive the exact grade and volume — that is what people search by. Listings with a price are viewed 2.4 times more often.\n4. Watch your incoming requests.\nYou see which company unlocked your contacts and from which listing.\n\n## If you are a buyer\n\n1. Search the catalogue or post a request.\nThe whole catalogue is visible without paying.\n2. Study the company before you call.\nDocuments, rating, reviews, time on the platform — all of it is open.\n3. Unlock the contact.\nA credit is spent per company, not per listing.","zh":"## 如果您是供应商\n\n1. 注册并验证邮箱。\n验证前可以使用后台，但无法发布。\n2. 填写企业资料。\n资料完整的企业收到的询盘多三倍。\n3. 发布信息。\n写明确切的牌号与数量 — 买家正是按此搜索。标价的信息被查看的次数多 2.4 倍。\n4. 关注收到的询盘。\n可以看到哪家企业从哪条信息解锁了您的联系方式。\n\n## 如果您是采购商\n\n1. 在目录中查找，或发布采购需求。\n整个目录无需付费即可浏览。\n2. 致电前先了解该企业。\n文件、评分、评价、入驻时长 — 全部公开。\n3. 解锁联系方式。\n额度按企业扣除，而非按信息条数。","tr":"## Tedarikçiyseniz\n\n1. Kayıt olun ve e-postanızı doğrulayın.\nDoğrulamadan önce panel açıktır, ancak ilan yayımlanamaz.\n2. Şirket kartınızı doldurun.\nEksiksiz profil üç kat daha fazla başvuru alır.\n3. İlan yayımlayın.\nTam markayı ve hacmi yazın — arama bunlarla yapılır. Fiyatı olan ilanlara 2,4 kat daha sık bakılır.\n4. Gelen talepleri izleyin.\nHangi şirketin iletişim bilgilerinizi hangi ilandan açtığı görünür.\n\n## Alıcıysanız\n\n1. Katalogdan bulun ya da bir talep yayımlayın.\nKatalog ödeme yapmadan tümüyle görünür.\n2. Aramadan önce şirketi inceleyin.\nBelgeler, puan, yorumlar, platformdaki süre — hepsi açıktır.\n3. İletişim bilgisini açın.\nKredi ilan başına değil, şirket başına düşer."}');
INSERT INTO public.pages VALUES (5, 'rules', 'rules', 'Правила размещения', 'Что можно и что нельзя публиковать на площадке.', '! Контактные данные в тексте объявления запрещены.
Телефон, почта, ссылки и ники в мессенджерах автоматически скрываются. Контакты передаются только через раскрытие контактов — на этом работает площадка.

## Что обязательно

- Достоверные название, ИНН и адрес компании
- Объявление в подходящей категории
- Реальные условия поставки, оплаты и объёмов
- Снятие объявления, когда товар закончился', NULL, NULL, true, 4, '2026-09-30 16:00:42', '2026-09-30 16:00:42', '{"uz":"Joylashtirish qoidalari","en":"Posting rules","zh":"发布规则","tr":"İlan kuralları"}', '{"uz":"Platformada nimani joylash mumkin va nimani mumkin emas.","en":"What you can and cannot publish on the platform.","zh":"平台上可以发布和禁止发布的内容。","tr":"Platformda neleri yayımlayabilir, neleri yayımlayamazsınız."}', '{"uz":"! E’lon matnida aloqa ma’lumotlari taqiqlanadi.\nTelefon, pochta, havolalar va messenjerdagi nomlar avtomatik yashiriladi. Kontaktlar faqat kontakt ochish orqali beriladi — maydon shunga asoslanadi.\n\n## Nima majburiy\n\n- Kompaniyaning haqiqiy nomi, STIRi va manzili\n- Mos toifadagi e’lon\n- Yetkazib berish, to‘lov va hajmning haqiqiy shartlari\n- Tovar tugaganda e’lonni olib tashlash","en":"! Contact details in the listing text are not allowed.\nPhone numbers, emails, links and messenger handles are hidden automatically. Contacts are passed only through contact unlocking — that is what the platform runs on.\n\n## What is required\n\n- A truthful company name, tax ID and address\n- A listing in the right category\n- Real terms of delivery, payment and volume\n- Taking the listing down when the goods run out","zh":"! 信息正文中禁止出现联系方式。\n电话、邮箱、链接和即时通讯账号会被自动隐藏。联系方式仅通过解锁传递 — 平台正是依此运转。\n\n## 必须做到\n\n- 真实的企业名称、税号与地址\n- 归入合适类别的信息\n- 真实的交付、付款与数量条件\n- 货品售罄时撤下信息","tr":"! İlan metninde iletişim bilgisi yasaktır.\nTelefon, e-posta, bağlantılar ve mesajlaşma kullanıcı adları otomatik olarak gizlenir. İletişim bilgileri yalnızca iletişim açma yoluyla verilir — platform buna dayanır.\n\n## Zorunlu olanlar\n\n- Şirketin gerçek unvanı, vergi numarası ve adresi\n- Uygun kategoride bir ilan\n- Gerçek teslimat, ödeme ve hacim koşulları\n- Ürün bittiğinde ilanın kaldırılması"}');


--
-- Data for Name: password_reset_tokens; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: payment_methods; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: payment_transactions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: payments; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: plans; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: platform_reviews; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: promo_codes; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: promotion_types; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: promotions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: refunds; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: resumes; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: reviews; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: search_hits; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: sessions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: settings; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.settings VALUES (1, 'contacts', 'office_coords', 'Координаты офиса', 'Широта и долгота через запятую, например: 41.311081, 69.240562. Взять их можно так: открыть Яндекс.Карты или Google Maps, нажать на здание правой кнопкой и скопировать координаты. Пока поле пустое, карта на странице не показывается — виден только адрес', 'string', '""', 6, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (2, 'contacts', 'office_map_zoom', 'Масштаб карты', 'От 3 до 19. 16 — дом и соседние кварталы, 12 — город целиком', 'number', '16', 7, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (3, 'legal', 'legal_full_name', 'Полное наименование', 'Точное наименование юридического лица как в учредительных документах. Показывается в разделе «Реквизиты» публичной оферты и в счёте', 'string', '"\"ANJIR-GROUP\" MAS''ULIYATI CHEKLANGAN JAMIYAT"', 20, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (4, 'legal', 'legal_brand', 'Торговое наименование', NULL, 'string', '"SavdEx"', 21, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (5, 'legal', 'legal_tin', 'ИНН', 'Должен совпадать с ИНН в публичной оферте — расхождение блокирует проверку банка-эквайера', 'string', '"312525684"', 22, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (6, 'legal', 'legal_address', 'Юридический адрес', NULL, 'string', '"Toshkent shahri, Shayxontohur tumani, Hadra MFY, Hadra mavzesi, 5-uy, 54-xonadon"', 23, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (7, 'legal', 'legal_actual_address', 'Фактический адрес', NULL, 'string', '"Toshkent shahri, Shayxontohur tumani, Furkat 1\/1"', 24, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (8, 'legal', 'legal_phone', 'Телефон юридического лица', 'Телефон из реквизитов оферты. Телефон поддержки для посетителей задаётся отдельно, в группе «Контакты»', 'string', '"+998 90 031-30-77"', 25, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (9, 'legal', 'legal_email', 'E-mail юридического лица', 'Почта из реквизитов оферты. Почта поддержки задаётся отдельно, в группе «Контакты»', 'string', '"Infoanjirgroup@gmail.com"', 26, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (10, 'legal', 'legal_bank', 'Банк', NULL, 'string', '"\"IPAK YO''LI\" AIT Banking Bosh O''fisi"', 27, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (11, 'legal', 'legal_mfo', 'Код банка (МФО)', NULL, 'string', '"00444"', 28, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (12, 'legal', 'legal_account', 'Расчётный счёт', NULL, 'string', '"20208000507335080001"', 29, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (13, 'legal', 'legal_director', 'Руководитель', NULL, 'string', '"ABDUHAMIDOV ABDURASHID ABDUVOHID OGLI"', 30, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (14, 'appearance', 'hero_image', 'Фон первого экрана', 'Картинка за заголовком на главной. Широкая горизонтальная, от 1920 px: она обрезается по центру и затемняется, чтобы читался белый текст. Пустое поле возвращает картинку по умолчанию', 'image', '""', 5, '2026-09-30 16:00:41', '2026-09-30 16:00:41');
INSERT INTO public.settings VALUES (15, 'appearance', 'logo_image', 'Логотип площадки', 'Знак в шапке, в подвале, на вкладке браузера и в админке. Квадратный, от 512 px; лучше SVG или PNG с прозрачным фоном — знак стоит и на белом, и на тёмно-синем. Пустое поле возвращает знак по умолчанию', 'image', '""', 6, '2026-09-30 16:00:42', '2026-09-30 16:00:42');
INSERT INTO public.settings VALUES (16, 'currency', 'display_currency_ru', 'Валюта на версии «Русский»', 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»', 'string', '"UZS"', 31, '2026-09-30 16:00:42', '2026-09-30 16:00:42');
INSERT INTO public.settings VALUES (17, 'currency', 'display_currency_uz', 'Валюта на версии «O‘zbekcha»', 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»', 'string', '"UZS"', 32, '2026-09-30 16:00:42', '2026-09-30 16:00:42');
INSERT INTO public.settings VALUES (18, 'currency', 'display_currency_en', 'Валюта на версии «English»', 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»', 'string', '"USD"', 33, '2026-09-30 16:00:42', '2026-09-30 16:00:42');
INSERT INTO public.settings VALUES (19, 'currency', 'display_currency_zh', 'Валюта на версии «中文»', 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»', 'string', '"CNY"', 34, '2026-09-30 16:00:42', '2026-09-30 16:00:42');
INSERT INTO public.settings VALUES (20, 'currency', 'display_currency_tr', 'Валюта на версии «Türkçe»', 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»', 'string', '"TRY"', 35, '2026-09-30 16:00:42', '2026-09-30 16:00:42');


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: support_messages; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: support_tickets; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: tenders; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: user_notifications; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: wallet_transactions; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: wallets; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Name: activity_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.activity_events_id_seq', 1, false);


--
-- Name: admin_actions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.admin_actions_id_seq', 1, false);


--
-- Name: audience_views_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.audience_views_id_seq', 1, false);


--
-- Name: banner_images_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.banner_images_id_seq', 1, false);


--
-- Name: banners_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.banners_id_seq', 1, false);


--
-- Name: broadcasts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.broadcasts_id_seq', 1, false);


--
-- Name: categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.categories_id_seq', 1, false);


--
-- Name: category_fields_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.category_fields_id_seq', 1, false);


--
-- Name: category_translations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.category_translations_id_seq', 1, false);


--
-- Name: cities_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.cities_id_seq', 1, false);


--
-- Name: city_translations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.city_translations_id_seq', 1, false);


--
-- Name: companies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.companies_id_seq', 1, false);


--
-- Name: company_attributes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_attributes_id_seq', 1, false);


--
-- Name: company_category_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_category_id_seq', 1, false);


--
-- Name: company_contacts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_contacts_id_seq', 1, false);


--
-- Name: company_documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_documents_id_seq', 1, false);


--
-- Name: company_invitations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_invitations_id_seq', 1, false);


--
-- Name: company_site_products_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_site_products_id_seq', 1, false);


--
-- Name: company_sites_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_sites_id_seq', 1, false);


--
-- Name: company_type_translations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_type_translations_id_seq', 25, true);


--
-- Name: company_types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.company_types_id_seq', 5, true);


--
-- Name: contact_unlocks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.contact_unlocks_id_seq', 1, false);


--
-- Name: content_translations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.content_translations_id_seq', 1, false);


--
-- Name: countries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.countries_id_seq', 1, false);


--
-- Name: country_translations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.country_translations_id_seq', 1, false);


--
-- Name: credit_packs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.credit_packs_id_seq', 3, true);


--
-- Name: crm_communications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.crm_communications_id_seq', 1, false);


--
-- Name: crm_contacts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.crm_contacts_id_seq', 1, false);


--
-- Name: crm_deals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.crm_deals_id_seq', 1, false);


--
-- Name: crm_leads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.crm_leads_id_seq', 1, false);


--
-- Name: crm_tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.crm_tasks_id_seq', 1, false);


--
-- Name: exports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.exports_id_seq', 1, false);


--
-- Name: failed_import_rows_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.failed_import_rows_id_seq', 1, false);


--
-- Name: failed_jobs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.failed_jobs_id_seq', 1, false);


--
-- Name: faq_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.faq_items_id_seq', 5, true);


--
-- Name: favorites_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.favorites_id_seq', 1, false);


--
-- Name: imports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.imports_id_seq', 1, false);


--
-- Name: it_task_files_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.it_task_files_id_seq', 1, false);


--
-- Name: it_tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.it_tasks_id_seq', 1, false);


--
-- Name: jobs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.jobs_id_seq', 1, false);


--
-- Name: landing_blocks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.landing_blocks_id_seq', 11, true);


--
-- Name: listing_attributes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.listing_attributes_id_seq', 1, false);


--
-- Name: listing_images_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.listing_images_id_seq', 1, false);


--
-- Name: listing_stats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.listing_stats_id_seq', 1, false);


--
-- Name: listings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.listings_id_seq', 1, false);


--
-- Name: login_attempts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.login_attempts_id_seq', 1, false);


--
-- Name: message_threads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.message_threads_id_seq', 1, false);


--
-- Name: messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.messages_id_seq', 1, false);


--
-- Name: migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.migrations_id_seq', 150, true);


--
-- Name: news_posts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.news_posts_id_seq', 1, false);


--
-- Name: notification_preferences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notification_preferences_id_seq', 1, false);


--
-- Name: pages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.pages_id_seq', 5, true);


--
-- Name: payment_methods_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.payment_methods_id_seq', 1, false);


--
-- Name: payment_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.payment_transactions_id_seq', 1, false);


--
-- Name: payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.payments_id_seq', 1, false);


--
-- Name: plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.plans_id_seq', 1, false);


--
-- Name: platform_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.platform_reviews_id_seq', 1, false);


--
-- Name: promo_codes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.promo_codes_id_seq', 1, false);


--
-- Name: promotion_types_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.promotion_types_id_seq', 1, false);


--
-- Name: promotions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.promotions_id_seq', 1, false);


--
-- Name: refunds_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.refunds_id_seq', 1, false);


--
-- Name: resumes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.resumes_id_seq', 1, false);


--
-- Name: reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.reviews_id_seq', 1, false);


--
-- Name: search_hits_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.search_hits_id_seq', 1, false);


--
-- Name: settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.settings_id_seq', 20, true);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.subscriptions_id_seq', 1, false);


--
-- Name: support_messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.support_messages_id_seq', 1, false);


--
-- Name: support_tickets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.support_tickets_id_seq', 1, false);


--
-- Name: tenders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tenders_id_seq', 1, false);


--
-- Name: user_notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.user_notifications_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 1, false);


--
-- Name: wallet_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.wallet_transactions_id_seq', 1, false);


--
-- Name: wallets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.wallets_id_seq', 1, false);


--
-- Name: activity_events activity_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_events
    ADD CONSTRAINT activity_events_pkey PRIMARY KEY (id);


--
-- Name: admin_actions admin_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions
    ADD CONSTRAINT admin_actions_pkey PRIMARY KEY (id);


--
-- Name: audience_views audience_views_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audience_views
    ADD CONSTRAINT audience_views_pkey PRIMARY KEY (id);


--
-- Name: banner_images banner_images_banner_id_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banner_images
    ADD CONSTRAINT banner_images_banner_id_locale_unique UNIQUE (banner_id, locale);


--
-- Name: banner_images banner_images_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banner_images
    ADD CONSTRAINT banner_images_pkey PRIMARY KEY (id);


--
-- Name: banners banners_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banners
    ADD CONSTRAINT banners_pkey PRIMARY KEY (id);


--
-- Name: broadcasts broadcasts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_pkey PRIMARY KEY (id);


--
-- Name: cache_locks cache_locks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache_locks
    ADD CONSTRAINT cache_locks_pkey PRIMARY KEY (key);


--
-- Name: cache cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cache
    ADD CONSTRAINT cache_pkey PRIMARY KEY (key);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: categories categories_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_slug_unique UNIQUE (slug);


--
-- Name: category_fields category_fields_category_id_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_fields
    ADD CONSTRAINT category_fields_category_id_key_unique UNIQUE (category_id, key);


--
-- Name: category_fields category_fields_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_fields
    ADD CONSTRAINT category_fields_pkey PRIMARY KEY (id);


--
-- Name: category_translations category_translations_category_id_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_translations
    ADD CONSTRAINT category_translations_category_id_locale_unique UNIQUE (category_id, locale);


--
-- Name: category_translations category_translations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_translations
    ADD CONSTRAINT category_translations_pkey PRIMARY KEY (id);


--
-- Name: cities cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_pkey PRIMARY KEY (id);


--
-- Name: city_translations city_translations_city_id_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_translations
    ADD CONSTRAINT city_translations_city_id_locale_unique UNIQUE (city_id, locale);


--
-- Name: city_translations city_translations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_translations
    ADD CONSTRAINT city_translations_pkey PRIMARY KEY (id);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: companies companies_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_slug_unique UNIQUE (slug);


--
-- Name: company_attributes company_attributes_company_id_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_attributes
    ADD CONSTRAINT company_attributes_company_id_key_unique UNIQUE (company_id, key);


--
-- Name: company_attributes company_attributes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_attributes
    ADD CONSTRAINT company_attributes_pkey PRIMARY KEY (id);


--
-- Name: company_category company_category_company_id_category_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_category
    ADD CONSTRAINT company_category_company_id_category_id_unique UNIQUE (company_id, category_id);


--
-- Name: company_category company_category_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_category
    ADD CONSTRAINT company_category_pkey PRIMARY KEY (id);


--
-- Name: company_contacts company_contacts_company_id_type_value_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts
    ADD CONSTRAINT company_contacts_company_id_type_value_unique UNIQUE (company_id, type, value);


--
-- Name: company_contacts company_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts
    ADD CONSTRAINT company_contacts_pkey PRIMARY KEY (id);


--
-- Name: company_documents company_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_documents
    ADD CONSTRAINT company_documents_pkey PRIMARY KEY (id);


--
-- Name: company_invitations company_invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT company_invitations_pkey PRIMARY KEY (id);


--
-- Name: company_invitations company_invitations_token_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT company_invitations_token_unique UNIQUE (token);


--
-- Name: company_site_products company_site_products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_site_products
    ADD CONSTRAINT company_site_products_pkey PRIMARY KEY (id);


--
-- Name: company_sites company_sites_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_sites
    ADD CONSTRAINT company_sites_company_id_unique UNIQUE (company_id);


--
-- Name: company_sites company_sites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_sites
    ADD CONSTRAINT company_sites_pkey PRIMARY KEY (id);


--
-- Name: company_sites company_sites_subdomain_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_sites
    ADD CONSTRAINT company_sites_subdomain_unique UNIQUE (subdomain);


--
-- Name: company_type_translations company_type_translations_company_type_id_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_type_translations
    ADD CONSTRAINT company_type_translations_company_type_id_locale_unique UNIQUE (company_type_id, locale);


--
-- Name: company_type_translations company_type_translations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_type_translations
    ADD CONSTRAINT company_type_translations_pkey PRIMARY KEY (id);


--
-- Name: company_types company_types_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_types
    ADD CONSTRAINT company_types_code_unique UNIQUE (code);


--
-- Name: company_types company_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_types
    ADD CONSTRAINT company_types_pkey PRIMARY KEY (id);


--
-- Name: contact_unlocks contact_unlocks_company_id_target_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_company_id_target_company_id_unique UNIQUE (company_id, target_company_id);


--
-- Name: contact_unlocks contact_unlocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_pkey PRIMARY KEY (id);


--
-- Name: content_translations content_translations_hash_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_translations
    ADD CONSTRAINT content_translations_hash_locale_unique UNIQUE (hash, locale);


--
-- Name: content_translations content_translations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_translations
    ADD CONSTRAINT content_translations_pkey PRIMARY KEY (id);


--
-- Name: countries countries_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_code_unique UNIQUE (code);


--
-- Name: countries countries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.countries
    ADD CONSTRAINT countries_pkey PRIMARY KEY (id);


--
-- Name: country_translations country_translations_country_id_locale_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.country_translations
    ADD CONSTRAINT country_translations_country_id_locale_unique UNIQUE (country_id, locale);


--
-- Name: country_translations country_translations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.country_translations
    ADD CONSTRAINT country_translations_pkey PRIMARY KEY (id);


--
-- Name: credit_packs credit_packs_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_packs
    ADD CONSTRAINT credit_packs_code_unique UNIQUE (code);


--
-- Name: credit_packs credit_packs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_packs
    ADD CONSTRAINT credit_packs_pkey PRIMARY KEY (id);


--
-- Name: crm_communications crm_communications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_communications
    ADD CONSTRAINT crm_communications_pkey PRIMARY KEY (id);


--
-- Name: crm_contacts crm_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_contacts
    ADD CONSTRAINT crm_contacts_pkey PRIMARY KEY (id);


--
-- Name: crm_deals crm_deals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals
    ADD CONSTRAINT crm_deals_pkey PRIMARY KEY (id);


--
-- Name: crm_leads crm_leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_leads
    ADD CONSTRAINT crm_leads_pkey PRIMARY KEY (id);


--
-- Name: crm_tasks crm_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_tasks
    ADD CONSTRAINT crm_tasks_pkey PRIMARY KEY (id);


--
-- Name: exports exports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exports
    ADD CONSTRAINT exports_pkey PRIMARY KEY (id);


--
-- Name: failed_import_rows failed_import_rows_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_import_rows
    ADD CONSTRAINT failed_import_rows_pkey PRIMARY KEY (id);


--
-- Name: failed_jobs failed_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_pkey PRIMARY KEY (id);


--
-- Name: failed_jobs failed_jobs_uuid_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_jobs
    ADD CONSTRAINT failed_jobs_uuid_unique UNIQUE (uuid);


--
-- Name: faq_items faq_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faq_items
    ADD CONSTRAINT faq_items_pkey PRIMARY KEY (id);


--
-- Name: favorites favorites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_pkey PRIMARY KEY (id);


--
-- Name: favorites favorites_user_id_listing_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_user_id_listing_id_unique UNIQUE (user_id, listing_id);


--
-- Name: imports imports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imports
    ADD CONSTRAINT imports_pkey PRIMARY KEY (id);


--
-- Name: it_task_files it_task_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_task_files
    ADD CONSTRAINT it_task_files_pkey PRIMARY KEY (id);


--
-- Name: it_tasks it_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks
    ADD CONSTRAINT it_tasks_pkey PRIMARY KEY (id);


--
-- Name: it_tasks it_tasks_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks
    ADD CONSTRAINT it_tasks_slug_unique UNIQUE (slug);


--
-- Name: job_batches job_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_batches
    ADD CONSTRAINT job_batches_pkey PRIMARY KEY (id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: landing_blocks landing_blocks_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.landing_blocks
    ADD CONSTRAINT landing_blocks_key_unique UNIQUE (key);


--
-- Name: landing_blocks landing_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.landing_blocks
    ADD CONSTRAINT landing_blocks_pkey PRIMARY KEY (id);


--
-- Name: listing_attributes listing_attributes_listing_id_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_attributes
    ADD CONSTRAINT listing_attributes_listing_id_key_unique UNIQUE (listing_id, key);


--
-- Name: listing_attributes listing_attributes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_attributes
    ADD CONSTRAINT listing_attributes_pkey PRIMARY KEY (id);


--
-- Name: listing_images listing_images_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_images
    ADD CONSTRAINT listing_images_pkey PRIMARY KEY (id);


--
-- Name: listing_stats listing_stats_listing_id_date_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_stats
    ADD CONSTRAINT listing_stats_listing_id_date_unique UNIQUE (listing_id, date);


--
-- Name: listing_stats listing_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_stats
    ADD CONSTRAINT listing_stats_pkey PRIMARY KEY (id);


--
-- Name: listings listings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_pkey PRIMARY KEY (id);


--
-- Name: listings listings_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_slug_unique UNIQUE (slug);


--
-- Name: login_attempts login_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_attempts
    ADD CONSTRAINT login_attempts_pkey PRIMARY KEY (id);


--
-- Name: message_threads message_threads_it_task_id_buyer_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_it_task_id_buyer_company_id_unique UNIQUE (it_task_id, buyer_company_id);


--
-- Name: message_threads message_threads_listing_id_buyer_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_listing_id_buyer_company_id_unique UNIQUE (listing_id, buyer_company_id);


--
-- Name: message_threads message_threads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: migrations migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (id);


--
-- Name: news_posts news_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_posts
    ADD CONSTRAINT news_posts_pkey PRIMARY KEY (id);


--
-- Name: news_posts news_posts_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_posts
    ADD CONSTRAINT news_posts_slug_unique UNIQUE (slug);


--
-- Name: notification_preferences notification_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_pkey PRIMARY KEY (id);


--
-- Name: notification_preferences notification_preferences_user_id_event_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_user_id_event_unique UNIQUE (user_id, event);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: pages pages_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_key_unique UNIQUE (key);


--
-- Name: pages pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_pkey PRIMARY KEY (id);


--
-- Name: pages pages_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pages
    ADD CONSTRAINT pages_slug_unique UNIQUE (slug);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (email);


--
-- Name: payment_methods payment_methods_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_pkey PRIMARY KEY (id);


--
-- Name: payment_transactions payment_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_pkey PRIMARY KEY (id);


--
-- Name: payment_transactions payment_transactions_provider_provider_transaction_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_provider_provider_transaction_id_unique UNIQUE (provider, provider_transaction_id);


--
-- Name: payments payments_number_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_number_unique UNIQUE (number);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: plans plans_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_code_unique UNIQUE (code);


--
-- Name: plans plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);


--
-- Name: platform_reviews platform_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews
    ADD CONSTRAINT platform_reviews_pkey PRIMARY KEY (id);


--
-- Name: platform_reviews platform_reviews_user_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews
    ADD CONSTRAINT platform_reviews_user_id_unique UNIQUE (user_id);


--
-- Name: promo_codes promo_codes_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_code_unique UNIQUE (code);


--
-- Name: promo_codes promo_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_pkey PRIMARY KEY (id);


--
-- Name: promo_codes promo_codes_used_by_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_used_by_company_id_unique UNIQUE (used_by_company_id);


--
-- Name: promotion_types promotion_types_code_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotion_types
    ADD CONSTRAINT promotion_types_code_unique UNIQUE (code);


--
-- Name: promotion_types promotion_types_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotion_types
    ADD CONSTRAINT promotion_types_pkey PRIMARY KEY (id);


--
-- Name: promotions promotions_active_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_active_key_unique UNIQUE (active_key);


--
-- Name: promotions promotions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_pkey PRIMARY KEY (id);


--
-- Name: refunds refunds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);


--
-- Name: resumes resumes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_pkey PRIMARY KEY (id);


--
-- Name: resumes resumes_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_slug_unique UNIQUE (slug);


--
-- Name: resumes resumes_user_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_user_id_unique UNIQUE (user_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (id);


--
-- Name: reviews reviews_unique_per_deal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_unique_per_deal UNIQUE (company_id, author_company_id, listing_id);


--
-- Name: search_hits search_hits_company_id_query_date_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_hits
    ADD CONSTRAINT search_hits_company_id_query_date_unique UNIQUE (company_id, query, date);


--
-- Name: search_hits search_hits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_hits
    ADD CONSTRAINT search_hits_pkey PRIMARY KEY (id);


--
-- Name: sessions sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sessions
    ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);


--
-- Name: settings settings_key_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_key_unique UNIQUE (key);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: support_messages support_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_messages
    ADD CONSTRAINT support_messages_pkey PRIMARY KEY (id);


--
-- Name: support_tickets support_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_pkey PRIMARY KEY (id);


--
-- Name: tenders tenders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders
    ADD CONSTRAINT tenders_pkey PRIMARY KEY (id);


--
-- Name: tenders tenders_slug_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders
    ADD CONSTRAINT tenders_slug_unique UNIQUE (slug);


--
-- Name: user_notifications user_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notifications
    ADD CONSTRAINT user_notifications_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: wallet_transactions wallet_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT wallet_transactions_pkey PRIMARY KEY (id);


--
-- Name: wallets wallets_company_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_company_id_unique UNIQUE (company_id);


--
-- Name: wallets wallets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_pkey PRIMARY KEY (id);


--
-- Name: activity_events_company_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX activity_events_company_id_created_at_index ON public.activity_events USING btree (company_id, created_at);


--
-- Name: activity_events_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX activity_events_subject_type_subject_id_index ON public.activity_events USING btree (subject_type, subject_id);


--
-- Name: admin_actions_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX admin_actions_created_at_index ON public.admin_actions USING btree (created_at);


--
-- Name: admin_actions_section_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX admin_actions_section_created_at_index ON public.admin_actions USING btree (section, created_at);


--
-- Name: admin_actions_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX admin_actions_subject_type_subject_id_index ON public.admin_actions USING btree (subject_type, subject_id);


--
-- Name: admin_actions_user_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX admin_actions_user_id_created_at_index ON public.admin_actions USING btree (user_id, created_at);


--
-- Name: audience_views_target_company_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audience_views_target_company_id_created_at_index ON public.audience_views USING btree (target_company_id, created_at);


--
-- Name: audience_views_viewer_company_id_target_company_id_created_at_i; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX audience_views_viewer_company_id_target_company_id_created_at_i ON public.audience_views USING btree (viewer_company_id, target_company_id, created_at);


--
-- Name: banners_placement_is_active_sort_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX banners_placement_is_active_sort_index ON public.banners USING btree (placement, is_active, sort);


--
-- Name: cache_expiration_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cache_expiration_index ON public.cache USING btree (expiration);


--
-- Name: cache_locks_expiration_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cache_locks_expiration_index ON public.cache_locks USING btree (expiration);


--
-- Name: categories_parent_id_sort_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX categories_parent_id_sort_index ON public.categories USING btree (parent_id, sort);


--
-- Name: cities_country_id_is_active_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cities_country_id_is_active_index ON public.cities USING btree (country_id, is_active);


--
-- Name: cities_slug_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX cities_slug_index ON public.cities USING btree (slug);


--
-- Name: companies_country_id_city_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_country_id_city_id_index ON public.companies USING btree (country_id, city_id);


--
-- Name: companies_legal_form_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_legal_form_index ON public.companies USING btree (legal_form);


--
-- Name: companies_partner_tier_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_partner_tier_index ON public.companies USING btree (partner_tier);


--
-- Name: companies_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_status_index ON public.companies USING btree (status);


--
-- Name: companies_status_verification_level_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_status_verification_level_index ON public.companies USING btree (status, verification_level);


--
-- Name: companies_tin_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX companies_tin_index ON public.companies USING btree (tin);


--
-- Name: company_category_category_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX company_category_category_id_index ON public.company_category USING btree (category_id);


--
-- Name: company_contacts_company_id_type_sort_order_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX company_contacts_company_id_type_sort_order_index ON public.company_contacts USING btree (company_id, type, sort_order);


--
-- Name: company_documents_company_id_moderation_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX company_documents_company_id_moderation_status_index ON public.company_documents USING btree (company_id, moderation_status);


--
-- Name: company_invitations_company_id_email_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX company_invitations_company_id_email_index ON public.company_invitations USING btree (company_id, email);


--
-- Name: company_site_products_company_id_sort_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX company_site_products_company_id_sort_index ON public.company_site_products USING btree (company_id, sort);


--
-- Name: contact_unlocks_complaint_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contact_unlocks_complaint_status_index ON public.contact_unlocks USING btree (complaint_status);


--
-- Name: contact_unlocks_target_company_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contact_unlocks_target_company_id_created_at_index ON public.contact_unlocks USING btree (target_company_id, created_at);


--
-- Name: content_translations_translation_attempts_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX content_translations_translation_attempts_index ON public.content_translations USING btree (translation, attempts);


--
-- Name: countries_is_active_sort_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX countries_is_active_sort_index ON public.countries USING btree (is_active, sort);


--
-- Name: crm_communications_author_id_happened_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_communications_author_id_happened_at_index ON public.crm_communications USING btree (author_id, happened_at);


--
-- Name: crm_communications_happened_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_communications_happened_at_index ON public.crm_communications USING btree (happened_at);


--
-- Name: crm_communications_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_communications_subject_type_subject_id_index ON public.crm_communications USING btree (subject_type, subject_id);


--
-- Name: crm_contacts_company_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_contacts_company_id_index ON public.crm_contacts USING btree (company_id);


--
-- Name: crm_contacts_name_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_contacts_name_index ON public.crm_contacts USING btree (name);


--
-- Name: crm_deals_owner_id_stage_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_deals_owner_id_stage_index ON public.crm_deals USING btree (owner_id, stage);


--
-- Name: crm_deals_stage_expected_close_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_deals_stage_expected_close_at_index ON public.crm_deals USING btree (stage, expected_close_at);


--
-- Name: crm_leads_owner_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_leads_owner_id_status_index ON public.crm_leads USING btree (owner_id, status);


--
-- Name: crm_leads_status_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_leads_status_created_at_index ON public.crm_leads USING btree (status, created_at);


--
-- Name: crm_tasks_assignee_id_done_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_tasks_assignee_id_done_at_index ON public.crm_tasks USING btree (assignee_id, done_at);


--
-- Name: crm_tasks_due_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_tasks_due_at_index ON public.crm_tasks USING btree (due_at);


--
-- Name: crm_tasks_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX crm_tasks_subject_type_subject_id_index ON public.crm_tasks USING btree (subject_type, subject_id);


--
-- Name: failed_jobs_connection_queue_failed_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX failed_jobs_connection_queue_failed_at_index ON public.failed_jobs USING btree (connection, queue, failed_at);


--
-- Name: it_tasks_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX it_tasks_company_id_status_index ON public.it_tasks USING btree (company_id, status);


--
-- Name: it_tasks_service_type_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX it_tasks_service_type_status_index ON public.it_tasks USING btree (service_type, status);


--
-- Name: it_tasks_status_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX it_tasks_status_published_at_index ON public.it_tasks USING btree (status, published_at);


--
-- Name: jobs_queue_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_queue_index ON public.jobs USING btree (queue);


--
-- Name: landing_blocks_is_visible_sort_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX landing_blocks_is_visible_sort_index ON public.landing_blocks USING btree (is_visible, sort);


--
-- Name: listings_category_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX listings_category_id_status_index ON public.listings USING btree (category_id, status);


--
-- Name: listings_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX listings_company_id_status_index ON public.listings USING btree (company_id, status);


--
-- Name: listings_status_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX listings_status_published_at_index ON public.listings USING btree (status, published_at);


--
-- Name: login_attempts_email_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX login_attempts_email_index ON public.login_attempts USING btree (email);


--
-- Name: login_attempts_email_ip_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX login_attempts_email_ip_created_at_index ON public.login_attempts USING btree (email, ip, created_at);


--
-- Name: login_attempts_ip_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX login_attempts_ip_index ON public.login_attempts USING btree (ip);


--
-- Name: message_threads_buyer_company_id_last_message_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX message_threads_buyer_company_id_last_message_at_index ON public.message_threads USING btree (buyer_company_id, last_message_at);


--
-- Name: message_threads_seller_company_id_last_message_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX message_threads_seller_company_id_last_message_at_index ON public.message_threads USING btree (seller_company_id, last_message_at);


--
-- Name: messages_thread_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX messages_thread_id_created_at_index ON public.messages USING btree (thread_id, created_at);


--
-- Name: news_posts_is_published_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX news_posts_is_published_published_at_index ON public.news_posts USING btree (is_published, published_at);


--
-- Name: notifications_notifiable_type_notifiable_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX notifications_notifiable_type_notifiable_id_index ON public.notifications USING btree (notifiable_type, notifiable_id);


--
-- Name: payment_methods_company_id_is_default_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX payment_methods_company_id_is_default_index ON public.payment_methods USING btree (company_id, is_default);


--
-- Name: payment_transactions_payment_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX payment_transactions_payment_id_index ON public.payment_transactions USING btree (payment_id);


--
-- Name: payments_company_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX payments_company_id_created_at_index ON public.payments USING btree (company_id, created_at);


--
-- Name: payments_status_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX payments_status_created_at_index ON public.payments USING btree (status, created_at);


--
-- Name: platform_reviews_status_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX platform_reviews_status_created_at_index ON public.platform_reviews USING btree (status, created_at);


--
-- Name: promo_codes_used_at_is_active_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX promo_codes_used_at_is_active_index ON public.promo_codes USING btree (used_at, is_active);


--
-- Name: promotions_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX promotions_company_id_status_index ON public.promotions USING btree (company_id, status);


--
-- Name: promotions_listing_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX promotions_listing_id_status_index ON public.promotions USING btree (listing_id, status);


--
-- Name: refunds_payment_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX refunds_payment_id_index ON public.refunds USING btree (payment_id);


--
-- Name: refunds_status_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX refunds_status_created_at_index ON public.refunds USING btree (status, created_at);


--
-- Name: resumes_field_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resumes_field_index ON public.resumes USING btree (field);


--
-- Name: resumes_status_field_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resumes_status_field_index ON public.resumes USING btree (status, field);


--
-- Name: resumes_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resumes_status_index ON public.resumes USING btree (status);


--
-- Name: resumes_status_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resumes_status_published_at_index ON public.resumes USING btree (status, published_at);


--
-- Name: reviews_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reviews_company_id_status_index ON public.reviews USING btree (company_id, status);


--
-- Name: reviews_dispute_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reviews_dispute_status_index ON public.reviews USING btree (dispute_status);


--
-- Name: reviews_origin_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reviews_origin_index ON public.reviews USING btree (origin);


--
-- Name: reviews_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX reviews_status_index ON public.reviews USING btree (status);


--
-- Name: reviews_unique_per_company; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX reviews_unique_per_company ON public.reviews USING btree (company_id, author_company_id) WHERE (listing_id IS NULL);


--
-- Name: sessions_last_activity_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_last_activity_index ON public.sessions USING btree (last_activity);


--
-- Name: sessions_user_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sessions_user_id_index ON public.sessions USING btree (user_id);


--
-- Name: settings_group_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX settings_group_index ON public.settings USING btree ("group");


--
-- Name: subscriptions_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX subscriptions_company_id_status_index ON public.subscriptions USING btree (company_id, status);


--
-- Name: support_messages_ticket_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX support_messages_ticket_id_created_at_index ON public.support_messages USING btree (ticket_id, created_at);


--
-- Name: support_tickets_assignee_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX support_tickets_assignee_id_status_index ON public.support_tickets USING btree (assignee_id, status);


--
-- Name: support_tickets_status_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX support_tickets_status_created_at_index ON public.support_tickets USING btree (status, created_at);


--
-- Name: tenders_category_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX tenders_category_id_status_index ON public.tenders USING btree (category_id, status);


--
-- Name: tenders_status_deadline_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX tenders_status_deadline_at_index ON public.tenders USING btree (status, deadline_at);


--
-- Name: tenders_status_published_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX tenders_status_published_at_index ON public.tenders USING btree (status, published_at);


--
-- Name: user_notifications_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_notifications_subject_type_subject_id_index ON public.user_notifications USING btree (subject_type, subject_id);


--
-- Name: user_notifications_user_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_notifications_user_id_created_at_index ON public.user_notifications USING btree (user_id, created_at);


--
-- Name: user_notifications_user_id_read_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_notifications_user_id_read_at_index ON public.user_notifications USING btree (user_id, read_at);


--
-- Name: users_company_id_status_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX users_company_id_status_index ON public.users USING btree (company_id, status);


--
-- Name: users_email_active_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX users_email_active_unique ON public.users USING btree (email) WHERE (deleted_at IS NULL);


--
-- Name: users_telegram_chat_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX users_telegram_chat_id_index ON public.users USING btree (telegram_chat_id);


--
-- Name: wallet_transactions_company_id_created_at_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX wallet_transactions_company_id_created_at_index ON public.wallet_transactions USING btree (company_id, created_at);


--
-- Name: wallet_transactions_subject_type_subject_id_index; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX wallet_transactions_subject_type_subject_id_index ON public.wallet_transactions USING btree (subject_type, subject_id);


--
-- Name: activity_events activity_events_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_events
    ADD CONSTRAINT activity_events_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: audience_views audience_views_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audience_views
    ADD CONSTRAINT audience_views_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: audience_views audience_views_target_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audience_views
    ADD CONSTRAINT audience_views_target_company_id_foreign FOREIGN KEY (target_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: audience_views audience_views_viewer_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audience_views
    ADD CONSTRAINT audience_views_viewer_company_id_foreign FOREIGN KEY (viewer_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: banner_images banner_images_banner_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.banner_images
    ADD CONSTRAINT banner_images_banner_id_foreign FOREIGN KEY (banner_id) REFERENCES public.banners(id) ON DELETE CASCADE;


--
-- Name: broadcasts broadcasts_sent_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.broadcasts
    ADD CONSTRAINT broadcasts_sent_by_foreign FOREIGN KEY (sent_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: categories categories_parent_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_parent_id_foreign FOREIGN KEY (parent_id) REFERENCES public.categories(id) ON DELETE SET NULL;


--
-- Name: category_fields category_fields_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_fields
    ADD CONSTRAINT category_fields_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;


--
-- Name: category_translations category_translations_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.category_translations
    ADD CONSTRAINT category_translations_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;


--
-- Name: cities cities_country_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_country_id_foreign FOREIGN KEY (country_id) REFERENCES public.countries(id) ON DELETE CASCADE;


--
-- Name: city_translations city_translations_city_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_translations
    ADD CONSTRAINT city_translations_city_id_foreign FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE CASCADE;


--
-- Name: companies companies_city_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_city_id_foreign FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: companies companies_country_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_country_id_foreign FOREIGN KEY (country_id) REFERENCES public.countries(id) ON DELETE SET NULL;


--
-- Name: companies companies_verified_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_verified_by_foreign FOREIGN KEY (verified_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: company_attributes company_attributes_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_attributes
    ADD CONSTRAINT company_attributes_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_category company_category_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_category
    ADD CONSTRAINT company_category_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;


--
-- Name: company_category company_category_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_category
    ADD CONSTRAINT company_category_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_contacts company_contacts_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts
    ADD CONSTRAINT company_contacts_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_documents company_documents_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_documents
    ADD CONSTRAINT company_documents_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_documents company_documents_moderated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_documents
    ADD CONSTRAINT company_documents_moderated_by_foreign FOREIGN KEY (moderated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: company_invitations company_invitations_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT company_invitations_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_invitations company_invitations_invited_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT company_invitations_invited_by_foreign FOREIGN KEY (invited_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: company_site_products company_site_products_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_site_products
    ADD CONSTRAINT company_site_products_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_sites company_sites_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_sites
    ADD CONSTRAINT company_sites_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_type_translations company_type_translations_company_type_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_type_translations
    ADD CONSTRAINT company_type_translations_company_type_id_foreign FOREIGN KEY (company_type_id) REFERENCES public.company_types(id) ON DELETE CASCADE;


--
-- Name: contact_unlocks contact_unlocks_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: contact_unlocks contact_unlocks_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE SET NULL;


--
-- Name: contact_unlocks contact_unlocks_moderated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_moderated_by_foreign FOREIGN KEY (moderated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: contact_unlocks contact_unlocks_target_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_target_company_id_foreign FOREIGN KEY (target_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: contact_unlocks contact_unlocks_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contact_unlocks
    ADD CONSTRAINT contact_unlocks_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: country_translations country_translations_country_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.country_translations
    ADD CONSTRAINT country_translations_country_id_foreign FOREIGN KEY (country_id) REFERENCES public.countries(id) ON DELETE CASCADE;


--
-- Name: crm_communications crm_communications_author_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_communications
    ADD CONSTRAINT crm_communications_author_id_foreign FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: crm_communications crm_communications_contact_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_communications
    ADD CONSTRAINT crm_communications_contact_id_foreign FOREIGN KEY (contact_id) REFERENCES public.crm_contacts(id) ON DELETE SET NULL;


--
-- Name: crm_contacts crm_contacts_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_contacts
    ADD CONSTRAINT crm_contacts_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: crm_contacts crm_contacts_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_contacts
    ADD CONSTRAINT crm_contacts_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: crm_deals crm_deals_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals
    ADD CONSTRAINT crm_deals_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: crm_deals crm_deals_contact_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals
    ADD CONSTRAINT crm_deals_contact_id_foreign FOREIGN KEY (contact_id) REFERENCES public.crm_contacts(id) ON DELETE SET NULL;


--
-- Name: crm_deals crm_deals_lead_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals
    ADD CONSTRAINT crm_deals_lead_id_foreign FOREIGN KEY (lead_id) REFERENCES public.crm_leads(id) ON DELETE SET NULL;


--
-- Name: crm_deals crm_deals_owner_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_deals
    ADD CONSTRAINT crm_deals_owner_id_foreign FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: crm_leads crm_leads_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_leads
    ADD CONSTRAINT crm_leads_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: crm_leads crm_leads_contact_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_leads
    ADD CONSTRAINT crm_leads_contact_id_foreign FOREIGN KEY (contact_id) REFERENCES public.crm_contacts(id) ON DELETE SET NULL;


--
-- Name: crm_leads crm_leads_owner_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_leads
    ADD CONSTRAINT crm_leads_owner_id_foreign FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: crm_tasks crm_tasks_assignee_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_tasks
    ADD CONSTRAINT crm_tasks_assignee_id_foreign FOREIGN KEY (assignee_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: crm_tasks crm_tasks_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.crm_tasks
    ADD CONSTRAINT crm_tasks_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: exports exports_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.exports
    ADD CONSTRAINT exports_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: failed_import_rows failed_import_rows_import_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.failed_import_rows
    ADD CONSTRAINT failed_import_rows_import_id_foreign FOREIGN KEY (import_id) REFERENCES public.imports(id) ON DELETE CASCADE;


--
-- Name: faq_items faq_items_page_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.faq_items
    ADD CONSTRAINT faq_items_page_id_foreign FOREIGN KEY (page_id) REFERENCES public.pages(id) ON DELETE CASCADE;


--
-- Name: favorites favorites_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: favorites favorites_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: imports imports_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.imports
    ADD CONSTRAINT imports_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: it_task_files it_task_files_it_task_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_task_files
    ADD CONSTRAINT it_task_files_it_task_id_foreign FOREIGN KEY (it_task_id) REFERENCES public.it_tasks(id) ON DELETE CASCADE;


--
-- Name: it_tasks it_tasks_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks
    ADD CONSTRAINT it_tasks_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: it_tasks it_tasks_contractor_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks
    ADD CONSTRAINT it_tasks_contractor_company_id_foreign FOREIGN KEY (contractor_company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: it_tasks it_tasks_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.it_tasks
    ADD CONSTRAINT it_tasks_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: listing_attributes listing_attributes_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_attributes
    ADD CONSTRAINT listing_attributes_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: listing_images listing_images_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_images
    ADD CONSTRAINT listing_images_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: listing_stats listing_stats_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_stats
    ADD CONSTRAINT listing_stats_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: listings listings_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;


--
-- Name: listings listings_city_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_city_id_foreign FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: listings listings_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: listings listings_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: message_threads message_threads_buyer_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_buyer_company_id_foreign FOREIGN KEY (buyer_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: message_threads message_threads_it_task_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_it_task_id_foreign FOREIGN KEY (it_task_id) REFERENCES public.it_tasks(id) ON DELETE SET NULL;


--
-- Name: message_threads message_threads_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE SET NULL;


--
-- Name: message_threads message_threads_seller_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.message_threads
    ADD CONSTRAINT message_threads_seller_company_id_foreign FOREIGN KEY (seller_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: messages messages_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: messages messages_thread_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_thread_id_foreign FOREIGN KEY (thread_id) REFERENCES public.message_threads(id) ON DELETE CASCADE;


--
-- Name: messages messages_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: news_posts news_posts_author_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news_posts
    ADD CONSTRAINT news_posts_author_id_foreign FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: notification_preferences notification_preferences_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_preferences
    ADD CONSTRAINT notification_preferences_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: payment_methods payment_methods_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_methods
    ADD CONSTRAINT payment_methods_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: payment_transactions payment_transactions_payment_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_transactions
    ADD CONSTRAINT payment_transactions_payment_id_foreign FOREIGN KEY (payment_id) REFERENCES public.payments(id) ON DELETE CASCADE;


--
-- Name: payments payments_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: payments payments_confirmed_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_confirmed_by_foreign FOREIGN KEY (confirmed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: payments payments_credit_pack_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_credit_pack_id_foreign FOREIGN KEY (credit_pack_id) REFERENCES public.credit_packs(id) ON DELETE SET NULL;


--
-- Name: payments payments_payment_method_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_payment_method_id_foreign FOREIGN KEY (payment_method_id) REFERENCES public.payment_methods(id) ON DELETE SET NULL;


--
-- Name: payments payments_plan_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_plan_id_foreign FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE SET NULL;


--
-- Name: payments payments_promo_code_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_promo_code_id_foreign FOREIGN KEY (promo_code_id) REFERENCES public.promo_codes(id) ON DELETE SET NULL;


--
-- Name: payments payments_subscription_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_subscription_id_foreign FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE SET NULL;


--
-- Name: platform_reviews platform_reviews_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews
    ADD CONSTRAINT platform_reviews_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: platform_reviews platform_reviews_moderated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews
    ADD CONSTRAINT platform_reviews_moderated_by_foreign FOREIGN KEY (moderated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: platform_reviews platform_reviews_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_reviews
    ADD CONSTRAINT platform_reviews_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: promo_codes promo_codes_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: promo_codes promo_codes_plan_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_plan_id_foreign FOREIGN KEY (plan_id) REFERENCES public.plans(id) ON DELETE CASCADE;


--
-- Name: promo_codes promo_codes_subscription_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_subscription_id_foreign FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE SET NULL;


--
-- Name: promo_codes promo_codes_used_by_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_used_by_company_id_foreign FOREIGN KEY (used_by_company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: promo_codes promo_codes_used_by_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promo_codes
    ADD CONSTRAINT promo_codes_used_by_user_id_foreign FOREIGN KEY (used_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: promotions promotions_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;


--
-- Name: promotions promotions_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: promotions promotions_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: promotions promotions_promotion_type_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.promotions
    ADD CONSTRAINT promotions_promotion_type_id_foreign FOREIGN KEY (promotion_type_id) REFERENCES public.promotion_types(id);


--
-- Name: refunds refunds_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: refunds refunds_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: refunds refunds_decided_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_decided_by_foreign FOREIGN KEY (decided_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: refunds refunds_payment_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_payment_id_foreign FOREIGN KEY (payment_id) REFERENCES public.payments(id) ON DELETE CASCADE;


--
-- Name: resumes resumes_city_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_city_id_foreign FOREIGN KEY (city_id) REFERENCES public.cities(id) ON DELETE SET NULL;


--
-- Name: resumes resumes_country_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_country_id_foreign FOREIGN KEY (country_id) REFERENCES public.countries(id) ON DELETE SET NULL;


--
-- Name: resumes resumes_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resumes
    ADD CONSTRAINT resumes_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_author_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_author_company_id_foreign FOREIGN KEY (author_company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_author_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_author_user_id_foreign FOREIGN KEY (author_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: reviews reviews_contact_unlock_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_contact_unlock_id_foreign FOREIGN KEY (contact_unlock_id) REFERENCES public.contact_unlocks(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_created_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_created_by_foreign FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_listing_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_listing_id_foreign FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE SET NULL;


--
-- Name: reviews reviews_moderated_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_moderated_by_foreign FOREIGN KEY (moderated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: search_hits search_hits_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_hits
    ADD CONSTRAINT search_hits_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_granted_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_granted_by_foreign FOREIGN KEY (granted_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: subscriptions subscriptions_plan_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_foreign FOREIGN KEY (plan_id) REFERENCES public.plans(id);


--
-- Name: support_messages support_messages_author_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_messages
    ADD CONSTRAINT support_messages_author_id_foreign FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: support_messages support_messages_ticket_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_messages
    ADD CONSTRAINT support_messages_ticket_id_foreign FOREIGN KEY (ticket_id) REFERENCES public.support_tickets(id) ON DELETE CASCADE;


--
-- Name: support_tickets support_tickets_assignee_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_assignee_id_foreign FOREIGN KEY (assignee_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: support_tickets support_tickets_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: support_tickets support_tickets_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_tickets
    ADD CONSTRAINT support_tickets_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: tenders tenders_author_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders
    ADD CONSTRAINT tenders_author_id_foreign FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: tenders tenders_category_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders
    ADD CONSTRAINT tenders_category_id_foreign FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE SET NULL;


--
-- Name: tenders tenders_country_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenders
    ADD CONSTRAINT tenders_country_id_foreign FOREIGN KEY (country_id) REFERENCES public.countries(id) ON DELETE SET NULL;


--
-- Name: user_notifications user_notifications_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notifications
    ADD CONSTRAINT user_notifications_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: user_notifications user_notifications_sent_by_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notifications
    ADD CONSTRAINT user_notifications_sent_by_foreign FOREIGN KEY (sent_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: user_notifications user_notifications_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_notifications
    ADD CONSTRAINT user_notifications_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE SET NULL;


--
-- Name: wallet_transactions wallet_transactions_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT wallet_transactions_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: wallet_transactions wallet_transactions_user_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallet_transactions
    ADD CONSTRAINT wallet_transactions_user_id_foreign FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: wallets wallets_company_id_foreign; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wallets
    ADD CONSTRAINT wallets_company_id_foreign FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--



