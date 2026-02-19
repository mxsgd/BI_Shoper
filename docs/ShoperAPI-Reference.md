# Shoper REST API – referencja pod BI Shoper (PLAN.md)

> Skrócona referencja tylko tych zasobów API, które zasilają warstwę RAW i CORE.  
> Źródło: oficjalna dokumentacja Shoper (REST API).  
> Format: przystępny dla modeli językowych (wyszukiwanie po nazwie zasobu, pola, metody).

---

## 1. Czy API pozwala zrealizować PLAN.md od strony bazodanowej?

**Tak.** Wszystkie tabele warstwy RAW mają odpowiedniki w Shoper REST API:

| PLAN (RAW)        | Zasób API Shoper   | Uwagi |
|-------------------|--------------------|--------|
| raw_orders        | **Orders**         | Pełne: sum, status, payment_id, shipping_id, user_id, discount_*, origin (kanał), promo_code, is_paid, adresy. |
| raw_order_items   | **Order Products** | Pozycje zamówień: product_id, order_id, price, quantity, discount_perc, tax_value, name, code. |
| raw_products      | **Products**       | product_id, category_id, producer_id, stock (ceny, stany), translations (name), tax_id, add_date. |
| raw_customers     | **Users**          | user_id, email, firstname, lastname, date_add, lastvisit, discount, group_id (klienci = zarejestrowani użytkownicy). |
| raw_payments      | **Payments**       | Metody płatności (słownik). Order Transactions (transakcje) – dla wybranych aplikacji; na start wystarczy payment_id w Orders. |
| raw_shipments     | **Shippings**      | Metody dostawy (słownik). **Parcels** – przesyłki per zamówienie (opcjonalnie do RAW). |
| raw_categories    | **Categories**     | category_id, root, order, translations (name, seo_url). Categories Tree – drzewo (opcjonalnie). |
| raw_discounts     | **Promotion codes** + **Special offers** | Kody rabatowe (promo) + promocje produktowe (specjalne oferty). |

**Dodatkowo potrzebne:** **Statuses** – słownik statusów zamówień (mapowanie status_id → nazwa/typ).

**Wnioski:**  
- fact_orders / fact_order_items: dane z Orders + Order Products + Statuses + Shippings + Payments.  
- dim_customers: z Users + agregacje z Orders.  
- dim_products / dim_categories: z Products + Categories.  
- dim_date: generowany lokalnie (kalendarz).  
- Marża: wymaga ceny kosztu – Products mają `stock.price_wholesale` (cena hurtowa); koszt własny może być w metafield lub osobnym polu w sklepie.

---

## 2. Ogólne zasady API (na podstawie PLAN.md i dokumentacji)

- **Autoryzacja:** Bearer token w nagłówku `Authorization`.  
- **Baza URL:** `https://{sklep}/webapi/rest/` (np. `https://mk-foam.pl/webapi/rest/`).  
- **Filtry:** format `filters=json.dumps({"pole": wartość})` (NIE `filter[pole]`).  
- **Paginacja:** parametry `limit` i `page`; odpowiedź zwraca `count` i `pages`.  
- **Odpowiedź list:** element listy w `d["list"]` (może być dict lub list).  
- **Rate limiting:** przy 429 sprawdź nagłówek `Retry-After`.

---

## 3. Zasoby – struktura i pola (tylko istotne dla ETL/BI)

### Orders  
**Opis:** Zamówienia w sklepie.  
**Endpoint:** `/webapi/rest/orders` (GET list, GET get, POST insert, PUT update, DELETE delete).  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| order_id | integer | ID zamówienia |
| user_id | null\|integer | ID klienta (Users) |
| date | string | Data utworzenia (format daty) |
| status_date | string | Data ostatniej zmiany statusu |
| confirm_date | string | Data potwierdzenia |
| delivery_date | string | Data dostawy |
| status_id | integer | ID statusu (→ Statuses) |
| status | object | status_id, type (1=new, 2=opened, 3=closed, 4=not completed), color, order |
| sum | float | Suma zamówienia |
| payment_id | integer | ID metody płatności (→ Payments) |
| shipping_id | integer | ID metody dostawy (→ Shippings) |
| shipping_cost | float | Koszt dostawy |
| email | string | E-mail klienta |
| code | string | Kod zamówienia |
| confirm | boolean | Czy potwierdzone |
| currency_id | integer | Waluta |
| currency_rate | float | Kurs waluty |
| paid | float | Zapłacona kwota |
| discount_client | float | Rabat klienta (%) |
| discount_group | float | Rabat grupy (%) |
| discount_levels | float | Rabat progów (%) |
| discount_code | float | Rabat kodem (%) |
| promo_code | string | Użyty kod promocyjny |
| is_paid | boolean | Czy opłacone |
| total_products | integer | Liczba produktów |
| origin | integer | Źródło: 0=shop, 1=facebook, 2=mobile, 3=allegro, 4=webapi, 5=panel, 6=admin, 8=Google |
| billing_address | object | address_id, city, postcode, street1, street2, state, country, country_code, phone |
| delivery_address | object | jw. |

---

### Order Products  
**Opis:** Pozycje zamówienia (jeden produkt w zamówieniu).  
**Endpoint:** `/webapi/rest/order-products`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| id | integer | ID pozycji |
| order_id | integer | ID zamówienia |
| product_id | integer | ID produktu (0 = brak w katalogu) |
| stock_id | integer | ID wariantu (0 = brak w katalogu) |
| price | float | Cena |
| discount_perc | float | Rabat % |
| quantity | float | Ilość |
| name | string | Nazwa produktu |
| code | string | Kod produktu |
| tax | string | Nazwa stawki VAT |
| tax_value | float | Wartość VAT |
| unit | string | Jednostka |

---

### Products  
**Opis:** Produkty w sklepie.  
**Endpoint:** `/webapi/rest/products`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| product_id | integer | ID produktu |
| type | integer | 0=produkt, 1=bundle |
| producer_id | null\|integer | Producent (→ Producers) |
| category_id | integer | Główna kategoria |
| category_tree_id | integer | Kategoria w drzewie |
| tax_id | integer | Stawka VAT |
| add_date | string | Data dodania |
| edit_date | string | Data edycji |
| code | string | Kod |
| ean | string | EAN |
| currency_id | integer | Waluta |
| categories | integer[] | Lista ID kategorii |
| translations | object | (locale).name, .short_description, .description, .active, .lang_id, .seo_url |
| stock | object | stock_id, product_id, price, active, default, stock, code, ean, price_wholesale, price_special, availability_id |

---

### Users  
**Opis:** Zarejestrowani użytkownicy (klienci).  
**Endpoint:** `/webapi/rest/users`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| user_id | integer | ID użytkownika |
| email | string | E-mail |
| firstname | string | Imię |
| lastname | string | Nazwisko |
| date_add | string | Data rejestracji |
| lastvisit | string | Ostatnia wizyta |
| discount | float | Rabat % |
| active | boolean | Aktywny |
| group_id | integer | Grupa (→ User Groups) |
| origin | integer | 0=shop, 1=Facebook, 2=mobile, 3=Allegro |

---

### Payments  
**Opis:** Metody płatności (słownik).  
**Endpoint:** `/webapi/rest/payments`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| (name) | string | Nazwa silnika (np. "external") |
| translations | object | (locale).title, .description, .active, .lang_id |
| order | integer | Kolejność wyświetlania |

---

### Shippings  
**Opis:** Metody dostawy (słownik).  
**Endpoint:** `/webapi/rest/shippings`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| shipping_id | integer | ID metody |
| name | string | Nazwa |
| cost | float | Koszt (stały lub 0 przy zależnym) |
| tax_id | integer | VAT |
| free_shipping | float | Próg darmowej dostawy |
| active | boolean | Aktywna |
| engine | string | personal, pickupPoint, apaczka, pocztaPolska, paczkomaty itd. |
| translations | object | (locale).name, .description, .active |

---

### Categories  
**Opis:** Kategorie produktów.  
**Endpoint:** `/webapi/rest/categories`.  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| category_id | integer | ID kategorii |
| root | boolean | Czy kategoria główna |
| order | integer | Kolejność |
| translations | object | (locale).name, .description, .seo_url, .active, .lang_id |

---

### Promotion codes  
**Opis:** Kody rabatowe.  
**Endpoint:** `/webapi/rest/promotion-codes` (nazwa zasobu w API: Promotion codes).  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| name | string | Nazwa |
| code | string | Kod |
| discount_type | integer | Typ rabatu |
| discount | integer | Wartość rabatu |
| max_discount_amount | float | Maks. kwota rabatu |
| time_from | string | Ważny od (ISO_8601) |
| time_to | string | Ważny do |
| min_amount | float | Min. wartość zamówienia |
| usage_limit | integer | Limit użyć |
| peruser_limit | integer | Limit na użytkownika |
| active | integer | Aktywny |
| usage_count | integer | Liczba użyć |

---

### Special offers  
**Opis:** Promocje produktowe (specjalne oferty).  
**Endpoint:** `/webapi/rest/special-offers` (nazwa zasobu w API: Special offers).  
**Metody:** get, list, insert, update, delete.

| Pole | Typ | Opis |
|------|-----|------|
| promo_id | integer | ID promocji |
| product_id | integer | ID produktu |
| stock_id | integer | ID wariantu |
| discount | float | Rabat |
| discount_wholesale | float | Rabat hurt |
| discount_special | float | Rabat specjalny |
| date_from | string | Od |
| date_to | string | Do |
| discount_type | integer | 2=kwota, 3=procent |
| condition_type | integer | 1=cały produkt, 2=wybrane warianty |
| stocks | integer[] | ID wariantów (gdy condition_type=2) |

---

### Statuses  
**Opis:** Statusy zamówień (słownik). Tylko odczyt.  
**Endpoint:** `/webapi/rest/statuses`.  
**Metody:** get, list.

| Pole | Typ | Opis |
|------|-----|------|
| status_id | integer | ID statusu |
| type | integer | 1=new, 2=opened, 3=closed, 4=not completed |
| color | string | Kolor (hex) |
| order | integer | Kolejność |
| translations | object | (locale).name, .lang_id |

---

## 4. Mapowanie na warstwę CORE (krótko)

- **fact_orders:** Orders (order_id, user_id→customer_id, date→order_date, status_id→order_status z Statuses, sum→gross_value, shipping_cost→shipping_value, payment_id/shipping_id, origin→source_channel, promo_code→campaign, is_paid→payment_status, total_products→items_count). Net/tax/margin – wyliczyć z Order Products i ewentualnie Products (cena hurtowa).
- **fact_order_items:** Order Products (id→order_item_id, order_id, product_id, category_id z Products, quantity, price→unit_price_gross, discount_perc, tax_value, order_date z Orders).
- **dim_customers:** Users + agregacje z Orders (first_order_date, last_order_date, total_orders, total_revenue, city z adresu, customer_type, rfm_score – wyliczane).
- **dim_products:** Products (product_id, translations.name→product_name, category_id, producer→brand, stock.price→retail_price, stock.price_wholesale→cost_price, active).
- **dim_categories:** Categories (category_id, translations.name→category_name, parent z drzewa lub root/order).
- **dim_date:** Generowany lokalnie (date_id, day, month, year, week, quarter, is_weekend).

---

*Koniec referencji. Szukaj po nazwie zasobu (np. "Orders", "Order Products") lub po nazwie pola (np. "order_id", "status_id").*
