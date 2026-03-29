# Crappie House booking — guests & SendGrid email

The **CrappieHouseBookingPage** flow builds `checkoutBooking` with **`adults`** and **`children`** from the guest picker (including `children: 0` when there are no kids), plus `visitStart`, `visitEnd`, `dayCount`, `people`, `totalCents`, and related fields. That object is passed into checkout as **`booking`** and merged into the Square **POST** `/api/square/payments` body.

## Frontend payload normalization

When building **`bookingPayload`**, numeric guest fields should always be set so nothing is lost when spreading JSON:

- `adults: Number(booking.adults ?? 0)`
- `children: Number(booking.children ?? 0)`

So **`children` is always present** on `booking` in the request (including `0`). The backend passes that **`booking`** dict into `build_booking_dynamic_template_data(..., booking=...)` and `send_booking_confirmation_email(..., booking=booking_dict)` as-is.

If **`booking`** were ever missing (unexpected on the Crappie flow), a fallback can still supply `children: 0`, `adults`, and `people` from the guest form.

## SendGrid template logic (`email.html`)

- **`children: 0`** — the **children / door-code disclaimer** block is **hidden** (`booking_has_kids` is false).
- **`children` ≥ 1** — the disclaimer **shows** (same door code applies to children; minors must be accompanied by a responsible adult on the property).

After backend or template changes, **re-copy** the repo’s `email.html` (or `backend/templates/sendgrid/booking_confirmation.html`) into the **SendGrid dynamic template** HTML editor and save.

### Testing in SendGrid

Use test data with **`children: 1`** (or run `send_template_test_email`, which includes `children: 1`) so the disclaimer appears in previews.

## Backend reference

- `services/email_service.py` — `_booking_has_kids()`, `build_booking_dynamic_template_data`, `send_booking_confirmation_email`
- `apps/payments/views.py` — passes `booking_dict` into the confirmation email after a paid charge
