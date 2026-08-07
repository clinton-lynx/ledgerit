# Quantization quality comparison

Answer-quality tiebreaker between the three SmolLM3 quantizations under consideration. Telemetry (speed, memory) is measured separately; this compares what a human panel would actually read. Each question is run 2x per model against the exact same computed facts (the Finding is calculated once with pandas and reused across every model — only the narration varies), so per-model inconsistency is visible instead of hidden behind a single sample.

## Chat template bug (read this first)

Only `SmolLM3-Q4_K_M.gguf` carries `tokenizer.chat_template` metadata. The other two GGUFs have none — confirmed by loading each and inspecting `llm.metadata` directly. Without that metadata, llama_cpp's `create_chat_completion()` silently falls back to a generic **llama-2** chat format (`<<SYS>>...<</SYS>> [INST]...[/INST]`) instead of SmolLM3's actual ChatML-style template. The model was never trained on that format: it doesn't recognise the turn boundaries, so it either echoes the raw prompt back verbatim or degenerates into repeating `<<SYS>>` until it hits `max_tokens`. A first raw run of this script through the normal `explain.explain()` path — i.e. going through llama_cpp's auto-detected chat format per file — produced unusable output for **every single answer** from both under-templated models, on every question.

The results below work around this: the one working chat_template (from `SmolLM3-Q4_K_M`) is extracted and rendered manually with `jinja2`, then fed to all three models through the raw completion API (`create_completion`), bypassing llama_cpp's per-file auto-detection entirely. All three are the same base model and tokenizer family, so this makes the comparison apples-to-apples — a test of quantization quality, not of which GGUF happened to keep its chat metadata.

**This workaround lives only in `tests/compare_quants.py`.** It does not change `explain.py`'s production behaviour. If either alternate quantization is adopted via `LEDGERIT_MODEL_PATH`, this same chat-template gap must be fixed there too — either by re-exporting the GGUF with correct `tokenizer.chat_template` metadata, or by porting this script's manual-render approach into `explain.py` — or production answers will be the same garbage this script had to work around.

| Model | Telemetry (measured separately) |
|---|---|
| `SmolLM3-Q4_K_M` | 8.26 tok/s, 2863 MB |
| `smollm3-3b-q3_k_m` | 6.13 tok/s, 1976 MB |
| `smollm3-3b-iq4_xs-imat` | 6.04 tok/s, 2157 MB |

## Per-model summary

| Model | Mean answer length (chars) | Mean generation time | Unsupported numbers (hallucination check) |
|---|---|---|---|
| `SmolLM3-Q4_K_M` | 725 | 20.3s | **0** across 10 answers |
| `smollm3-3b-q3_k_m` | 756 | 20.8s | **0** across 10 answers |
| `smollm3-3b-iq4_xs-imat` | 653 | 19.3s | **0** across 10 answers |

"Unsupported numbers" above is the FINAL count — after every flagged answer already got one retry with a stronger instruction (see `explain.verify_and_retry`). It is not the raw first-pass hallucination rate; the retry table below shows that separately.

### Retry outcomes

| Model | Answers needing a retry | Fixed by retry | Still unverified after retry |
|---|---|---|---|
| `SmolLM3-Q4_K_M` | 1 / 10 | 1 | 0 |
| `smollm3-3b-q3_k_m` | 0 / 10 | 0 | 0 |
| `smollm3-3b-iq4_xs-imat` | 1 / 10 | 1 | 0 |

No unsupported numbers detected in any final answer, any model.

## Answers by question

Grouped by question, models side by side, so the same question's answers are directly comparable across models. Text shown is the FINAL text (after a retry, if one happened).

### "what are my best sellers?"

*Computed facts given to every model:*

```
Top 5 products by revenue
note: Soft Drink sells the most units (223) but Pounded Yam & Egusi earns the most revenue (NGN 559,732). Different margin profiles — one is volume, the other is value.
concentration: These 5 products are 55% of total revenue across 15 products sold.
            product revenue  units  orders
Pounded Yam & Egusi 559,732  221.0     140
      Amala & Ewedu 423,121  211.0     130
        Jollof Rice 320,352  178.0     115
         Fried Rice 284,757  157.0     104
         Eba & Okra 272,903  181.0     108
How to interpret this: These are the STRONGEST performers, ranked highest revenue first. They are what is working: candidates to protect stock of, promote further, or use as an anchor. Do NOT describe them as underperforming or as a risk.
```

**`SmolLM3-Q4_K_M`**

- Run 1 (30.5s) — retried:
  > The shop owner should focus on the top 5 products, as they account for 55% of total revenue. These products are the strongest performers, and their success can be leveraged to maintain or increase their market share. The owner should consider strategies to protect these top sellers, such as maintaining adequate stock levels, promoting them further, or using them as an anchor to attract other customers. The fact that the top 5 products generate 55% of the total revenue suggests that the business has a strong foundation in these key items, and it's advisable to build upon their success rather than risking diversification into other products that may not perform as well.
- Run 2 (11.4s):
  > The top 5 products account for 55% of the total revenue, indicating a strong concentration of sales in these key items. This suggests that the shop owner should focus on maintaining or increasing the stock and promotion of these products, as they are not only the most profitable but also contribute significantly to overall revenue. The fact that Pounded Yam & Egusi earns the most revenue despite selling fewer units compared to Soft Drink highlights the importance of considering both volume and value in product selection. The shop owner should consider strategies to enhance the visibility and appeal of these top performers to maximize their impact on the business.

**`smollm3-3b-q3_k_m`**

- Run 1 (15.3s):
  > These top 5 products are the backbone of the business, driving the majority of revenue. They are the best sellers, and their performance is strong enough to account for 55% of total revenue. This suggests that the business has a solid foundation with these products, which are likely to be popular among customers. Protecting these products, promoting them further, or using them as an anchor product can help maintain and grow revenue. The owner should focus on sustaining the success of these top performers, ensuring they remain a staple in the product line. Additionally, understanding the demand for these products can help inform inventory management and marketing strategies to maximize sales and profitability.
- Run 2 (17.1s):
  > The top 5 products account for 55% of the total revenue, indicating that these items are the core drivers of the business's revenue. This suggests that the business should prioritize these products to maintain and grow their revenue. Given that Pounded Yam & Egusi earns the most revenue, it is likely a best-seller, and the business should consider increasing its stock of this product and promoting it more aggressively. Additionally, since these 5 products account for a significant portion of the total revenue, the business should focus on understanding what makes these products so successful and replicate that success with other products. This could involve analyzing customer preferences, pricing, and product offerings to see how these top performers can be replicated or improved upon.

**`smollm3-3b-iq4_xs-imat`**

- Run 1 (17.9s):
  > These top 5 products are the backbone of your business, contributing to 55% of total revenue. They are the best sellers, not just in terms of units sold but also in revenue. This suggests that your core products are strong performers, and it's wise to focus on maintaining their popularity. Since Pounded Yam & Egusi earns the highest revenue, it's a candidate for being a flagship product. Meanwhile, the volume-oriented products like Soft Drink and Amala & Ewedu indicate that these items are in high demand, suggesting you should consider increasing their production to meet the demand. The remaining products, while contributing to the total revenue, are not as dominant. It's worth exploring opportunities to promote or adjust the offerings of these top performers to further boost their sales and revenue, ensuring they remain strong and profitable for your business.
- Run 2 (14.4s):
  > The top 5 products are the key drivers of the shop's revenue, accounting for 55% of the total revenue generated from all 15 products. This indicates that these products are not only the most profitable but also the most popular among customers. The shop owner should focus on maintaining or increasing the sales of these top performers to ensure sustained revenue growth. Additionally, the high concentration of revenue in these products suggests that the shop should consider strategies to further promote these items, such as marketing campaigns or discounts, to capitalize on their popularity and profitability. By doing so, the shop can reinforce its position as a leading player in the market and build on the success of its top-selling products.

### "worst sellers"

*Computed facts given to every model:*

```
5 weakest-selling products by revenue (lowest earners)
ranking: These are the 5 LOWEST-earning products out of 15 total products sold, ordered worst-earner first. They are the bottom of the list, not the top.
share: Combined, these 5 weakest products brought in only 14% of total revenue — a small, not a large, slice of the business.
volume warning: Soft Drink, Moi Moi rank low on revenue but are also among the top 5 products by units sold — low price, not low demand. Repricing is more appropriate than discontinuing for these.
         product revenue  units  orders
   Bottled Water  37,278  186.0     123
      Soft Drink  90,809  223.0     129
Puff Puff (6Pcs)  94,088  188.0     117
            Zobo  95,321  190.0     127
         Moi Moi 148,064  210.0     125
How to interpret this: These are the WEAKEST performers by revenue. They are candidates to drop, reprice or promote — not products the business depends on. Do NOT describe them as a concentration risk, as important to the business, or advise 'reducing dependence' on them; low revenue means the opposite of dependence. EXCEPTION: if a 'volume warning' fact is present, the products it names sell in high volume at a low price — they are not low-demand and should NOT be described as candidates to drop or discontinue. For those specific products, recommend repricing instead.
```

**`SmolLM3-Q4_K_M`**

- Run 1 (24.3s):
  > The shop owner should focus on the five weakest-selling products by revenue, which account for only 14% of total revenue. These products, including Bottled Water, Soft Drink, Puff Puff, Zobo, and Moi Moi, are not critical to the business's overall performance. However, they do sell in high volume at a low price, indicating low pricing strategy rather than low demand. The shop owner should consider repricing these products rather than discontinuing them, as they are not low-demand items. This approach could potentially increase revenue without significantly impacting the business's overall performance.
- Run 2 (22.1s):
  > The shop owner should focus on the 5 weakest-selling products by revenue, as they account for only 14% of the total revenue. These products, including Bottled Water, Soft Drink, Puff Puff (6Pcs), Zobo, and Moi Moi, are not critical to the business's overall performance. The shop owner should consider repricing these products rather than discontinuing them, especially since Soft Drink and Moi Moi are also among the top 5 products by units sold. This suggests that these products have low price points, not low demand, and could benefit from a price adjustment to increase revenue without affecting the high volume of sales. The shop owner should explore pricing strategies to boost the revenue from these products, rather than focusing on reducing dependence on them, as they are not the backbone of the business.

**`smollm3-3b-q3_k_m`**

- Run 1 (34.9s):
  > The shop owner should focus on the Bottled Water, Soft Drink, and Puff Puff (6Pcs) products, as they are the weakest performers by revenue. These products bring in a small portion of the total revenue, and their combined sales only account for 14% of the overall revenue. This suggests that these products are not critical to the business's overall performance.

However, the Soft Drink and Moi Moi products are exceptions. The Soft Drink and Moi Moi are among the top 5 products by units sold, despite their low revenue. This indicates that these products have high volume sales at a low price. Therefore, the owner should reconsider repricing these products rather than discontinuing them. The owner should focus on the Bottled Water, Puff Puff (6Pcs), and Zobo products, which are the weakest performers and can be considered for discontinuation or repricing.
- Run 2 (18.8s):
  > The shop owner should focus on the Bottled Water, Soft Drink, Puff Puff (6Pcs), Zobo, and Moi Moi products, as they are the weakest performers by revenue. These products account for only 14% of total revenue, indicating they are not a significant part of the business. However, the Soft Drink and Moi Moi products have a warning about being low-priced but high in volume, suggesting they are not low-demand. For these specific products, the owner should consider repricing instead of discontinuing them. The owner should not view these products as a concentration risk or a key part of the business, as their low revenue suggests they are not essential to the business's overall performance.

**`smollm3-3b-iq4_xs-imat`**

- Run 1 (24.9s):
  > The shop owner should consider discontinuing or repricing Bottled Water, Soft Drink, Puff Puff (6Pcs), Zobo, and Moi Moi, as they are the weakest-selling products by revenue. These products contribute only 14% of the total revenue, indicating they are not a significant part of the business's income. However, Soft Drink and Moi Moi are among the top 5 products by units sold, suggesting they have high demand despite their low revenue. For these specific products, the business should focus on repricing rather than discontinuing them. Bottled Water, Puff Puff (6Pcs), and Zobo, on the other hand, are not among the top-selling products by units, making them stronger candidates for discontinuation or repricing.
- Run 2 (14.4s):
  > The shop owner should consider discontinuing or repricing the Bottled Water, Soft Drink, Puff Puff, Zobo, and Moi Moi products, as they are the weakest performers by revenue. These products account for only 14% of total revenue, indicating they are not a significant part of the business's income. However, the Soft Drink and Moi Moi products also rank among the top 5 in units sold, suggesting they have a strong demand. Therefore, instead of discontinuing these products, the owner should consider repricing them to increase their revenue potential. This approach would allow the shop to capitalize on the high volume sales while also improving profitability.

### "am I doing better than last month?"

*Computed facts given to every model:*

```
Revenue by month
latest change: +1.8% vs previous month
range: Best month May 2026 (NGN 1,230,669), weakest Jun 2026 (NGN 1,074,875).
   month   revenue  orders
May 2026 1,230,669     650
Jun 2026 1,074,875     585
Jul 2026 1,094,653     580
How to interpret this: The table is in calendar order, not ranked. A rising revenue figure month over month is good news; a falling one is a warning sign. The 'weakest' month in the range note is a low point, not the norm — do not generalise a single weak month into 'the business is dead'.
```

**`SmolLM3-Q4_K_M`**

- Run 1 (24.1s):
  > The shop owner is seeing a slight increase in revenue from May to June, but the revenue has been fluctuating. May was the best month, with a revenue of NGN 1,230,669, while June was the weakest month, with revenue of NGN 1,074,875. July saw a slight improvement, with revenue of NGN 1,094,653. This fluctuation suggests that the business is not consistently performing well, and the owner should not assume that June's performance is indicative of the overall business health. Instead, the owner should monitor the trend over multiple months to determine if the business is on a path to sustained growth or if there are underlying issues affecting performance. The owner should also investigate the reasons behind the fluctuations, such as changes in customer demand, pricing, or operational efficiency, to make informed decisions.
- Run 2 (11.6s):
  > The shop owner is seeing a slight increase in revenue from May to June, but the revenue in June is lower than the previous month. However, when looking at the range, May is the best month with the highest revenue, and June is the weakest, but not a consistent trend. The revenue in July is higher than June, indicating a possible recovery. This suggests that the shop owner should focus on addressing the issues that led to the June decline, as the business has shown resilience in the past. It's also worth monitoring the trend over the next few months to ensure the recovery is sustainable.

**`smollm3-3b-q3_k_m`**

- Run 1 (23.6s):
  > The business is showing a positive trend with revenue increasing by 1.8% compared to the previous month. However, the revenue range indicates that May was the best month, with the highest revenue of NGN 1,230,669, while June was the weakest, with the lowest revenue of NGN 1,074,875. This suggests that the business experienced a slight dip in June, but the overall trend is still positive. The revenue in July (NGN 1,094,653) is higher than June, indicating that the business is recovering from the dip in June. The owner should focus on understanding the reasons behind the dip in June and addressing any underlying issues to ensure the business continues to grow.
- Run 2 (13.4s):
  > The revenue figures show a slight increase of 1.8% from June to July, indicating a positive trend. However, the revenue in June was lower than in May, which was the best month of the range. The business experienced a slight dip in June, but the overall trend is still upward. This suggests that the business is generally doing better than last month, but the owner should monitor the trend to ensure it continues. The dip in June shouldn't be taken as a permanent setback, but the owner should investigate the reasons behind the drop to prevent it from recurring.

**`smollm3-3b-iq4_xs-imat`**

- Run 1 (19.5s):
  > The increasing revenue of NGN 1,094,653 in July compared to June's NGN 1,074,875 indicates a positive trend of growth. However, the revenue in June was lower than in May, suggesting a slight dip. This dip is not alarming, as the overall trend is upward, and June's lower revenue is likely an anomaly. The business is not dead, but the owner should monitor the June dip to ensure it doesn't become a recurring issue. It may be worth investigating the factors behind the June dip to prevent similar fluctuations in the future.
- Run 2 (33.8s) — retried:
  > The shop owner's revenue increased by 1.8% from June to July, indicating a positive trend. However, the revenue in June was lower than in May, but not as low as the weakest month, which was June itself. This suggests that the shop is generally improving, but there was a temporary dip in June. The business should focus on maintaining the upward trend and addressing the specific issue that caused the June dip, rather than generalizing the June performance as a sign of decline.

### "which day is quietest?"

*Computed facts given to every model:*

```
Revenue by day of week, weakest first
spread: QUIETEST day: Friday, NGN 419,944. BUSIEST day: Saturday, NGN 638,626. Busiest earns 1.5x what quietest does.
weekend effect: HIGHER-earning: weekends average NGN 585,230 per day. LOWER-earning: weekdays average NGN 445,947 per day.
      dow revenue  orders
   Friday 419,944     240
 Thursday 428,289     246
Wednesday 435,534     217
   Monday 467,542     247
  Tuesday 478,428     248
   Sunday 531,834     289
 Saturday 638,626     328
How to interpret this: The table is sorted weakest day first, busiest day last — and the 'spread' fact labels each end explicitly with the words QUIETEST and BUSIEST. The quietest day has the LOWEST revenue, fewest customers, and is the closest thing to 'when is the shop dead' — a candidate for shorter hours, a promotion, or closing altogether. The busiest day has the HIGHEST revenue. Do NOT swap these two: whichever day is named 'QUIETEST' in the spread fact is the weak one, not the strong one, no matter which day it appears next to in the sentence.
```

**`SmolLM3-Q4_K_M`**

- Run 1 (31.9s):
  > The quietest day, Friday, generates the lowest revenue (NGN 419,944) and has the fewest customers (240 orders). This suggests that Friday could be a slow period for the shop, potentially due to local events, holidays, or other factors. The owner should consider adjusting their schedule or promotions to capitalize on this quiet period, such as offering discounts or extending hours to attract more customers during the week. The busiest day, Saturday, generates significantly higher revenue (NGN 638,626) and has the most customers (328 orders), indicating that Saturday is the peak shopping day for the shop. The owner should also consider maintaining or increasing staffing levels on Saturdays to meet the higher demand.
- Run 2 (16.4s):
  > The quietest day, Friday, generates the lowest revenue (NGN 419,944) and has the fewest customers (240 orders). This suggests that Friday could be a good candidate for reducing hours, offering promotions, or even closing the shop to minimize losses. On the other hand, the busiest day, Saturday, generates the highest revenue (NGN 638,626) and has the most customers (328 orders). This indicates that Saturday is the most profitable day, and the shop might consider extending hours, offering special promotions, or increasing staffing to capitalize on this peak demand. The weekend effect also shows that the shop earns more on weekends, with an average of NGN 585,230 per day, compared to weekdays averaging NGN 445,947 per day. This could inform staffing and resource allocation decisions to ensure the shop is adequately covered during peak weekend periods.

**`smollm3-3b-q3_k_m`**

- Run 1 (25.6s):
  > The quietest day is Friday, with revenue of NGN 419,944 and 240 orders. This is significantly lower than the busiest day, Saturday, which has revenue of NGN 638,626 and 328 orders. The revenue difference between the quietest and busiest days is substantial, with the busiest day earning 1.5 times more than the quietest day. 

The business should consider the quietest day as a candidate for reducing hours, offering promotions, or closing altogether to optimize operations. The weekend effect shows that days like Saturday and Sunday have higher average revenue, which could be due to increased foot traffic or other factors. However, the quietest day, Friday, is a concern that requires attention to ensure the business is not losing potential revenue.
- Run 2 (12.4s):
  > The quietest day, Friday, has significantly lower revenue and fewer customers compared to the busiest day, Saturday. This suggests that the shop experiences a decline in activity and sales on Fridays. Given the revenue difference, the shop owner might consider adjusting their hours or promotions to capitalize on the higher revenue days, such as Saturday and Sunday. Additionally, the weekend effect indicates that the shop earns more on weekends, which could be a good time to increase marketing efforts or offer special weekend deals to attract more customers during these quieter days.

**`smollm3-3b-iq4_xs-imat`**

- Run 1 (20.5s):
  > The quietest day, Friday, generates significantly lower revenue and has fewer customers compared to the busiest day, Saturday. This suggests that Friday is a low-traffic day for the shop, which might be a good candidate for reducing hours, offering promotions, or closing altogether to minimize losses. The weekend effect shows that weekends, on average, earn more than weekdays, which is consistent with the quietest day being a weekday. The shop owner should consider adjusting their operations on Fridays to better align with customer demand and revenue potential.
- Run 2 (14.7s):
  > The quietest day, Friday, has significantly lower revenue and fewer customers compared to the busiest day, Saturday. This suggests that Friday is the least profitable day for the shop. The owner should consider whether reducing hours or offering promotions on Friday could help increase sales and make the shop more attractive to customers. Additionally, the weekend effect shows that weekends on average earn more than weekdays, indicating that the shop benefits from the higher customer traffic during these periods. However, the quietest day is a notable exception, and the owner may want to explore strategies to boost sales on Fridays, such as adjusting the store's hours or offering special deals to attract more customers during this time.

### "how do customers pay me?"

*Computed facts given to every model:*

```
Revenue by payment method
basket size: Orders via cash average NGN 1,906 versus NGN 1,553 via unknown.
data gap: 2% of revenue has no payment method recorded.
payment_method   revenue  orders share %
          card 1,474,531     780    43.4
          cash   977,630     513    28.8
      transfer   864,189     468    25.4
       unknown    83,847      54     2.5
How to interpret this: Rows are ranked highest revenue first, lowest last. The top row is the strongest payment method; the bottom row is the weakest. If a 'concentration risk' fact is present, that describes over-reliance on the TOP row, which is a fragility to flag, not an achievement to praise.
```

**`SmolLM3-Q4_K_M`**

- Run 1 (19.0s):
  > The data suggests that the shop owner relies heavily on card payments, which account for 43.4% of total revenue. This is the strongest payment method, indicating that customers prefer using cards for their purchases. However, the shop owner should be cautious, as the second strongest payment method, cash, only accounts for 28.8% of revenue. This disparity could indicate a concentration risk, where the shop owner is overly reliant on card payments and may be vulnerable to disruptions if card services are unavailable. Additionally, the 2% of revenue with no payment method recorded could indicate a need to improve data collection or customer payment preferences. The shop owner should consider diversifying payment methods to reduce risk and enhance customer convenience.
- Run 2 (11.6s):
  > The data suggests that the shop owner relies heavily on card payments, which account for 43.4% of the total revenue. This is the strongest payment method, indicating that customers prefer using credit cards for their purchases. However, this also means that a significant portion of the business is vulnerable to disruptions in card payment services, such as technical issues or fraud. The owner should consider diversifying their payment methods to reduce this risk and ensure a stable cash flow. Additionally, the data gap of 2% of revenue with no payment method recorded could indicate issues with certain customers or transactions, which the owner should investigate to prevent potential losses.

**`smollm3-3b-q3_k_m`**

- Run 1 (24.5s):
  > The data suggests that the majority of revenue is generated through card payments, accounting for 43.4% of total revenue. This is the strongest payment method, indicating that customers prefer using cards over cash or other methods. However, the fact that only 2.5% of revenue has no payment method recorded raises concerns about data completeness and potential fraud or errors in recording cash transactions. 

The business relies heavily on card payments, which is a strong point, but the lack of data for unknown payment methods could indicate gaps in their payment processing system. This fragility in data collection might lead to inconsistencies in financial reporting and make it harder to accurately assess the effectiveness of different payment methods. The business should consider improving their payment processing system to ensure complete and accurate data for all transactions.
- Run 2 (22.7s):
  > The data indicates that customers predominantly use cash for payments, accounting for 28.8% of total revenue. However, credit card transactions are the highest revenue generator, accounting for 43.4% of total revenue. This suggests that while credit cards are the most profitable method, cash transactions are more common, which could indicate that customers prefer to pay with cash. The low percentage of unknown payment methods (2.5%) indicates that there is a clear preference for known payment methods. 

This information is crucial for the business owner to consider when deciding on payment options and strategies. If the business relies heavily on cash transactions, it may be beneficial to explore ways to increase the use of credit cards, such as offering discounts or rewards for customers who pay with credit cards. Additionally, the business may want to consider the reasons behind the preference for cash payments, such as convenience or security, and address any concerns that may be influencing customer behavior.

**`smollm3-3b-iq4_xs-imat`**

- Run 1 (18.9s):
  > The data indicates that card payments are the most popular method of payment, accounting for 43.4% of the total revenue, followed by cash at 28.8%. This suggests that the shop owner relies heavily on card transactions, which could be a concentration risk. If the majority of transactions are via card, the business may be vulnerable to issues like card fraud or technical payment problems. It's worth considering diversifying payment methods, such as adding more cash options or accepting mobile payments, to reduce reliance on a single method and mitigate potential risks.
- Run 2 (13.9s):
  > The figures suggest that the shop owner relies heavily on card payments, accounting for 43.4% of total revenue. This is the strongest payment method, but it also poses a concentration risk, as a significant portion of revenue (28.8%) comes from cash, and a smaller but notable amount from transfers. The 'unknown' payment method accounts for only 2.5% of revenue, indicating a data gap that should be addressed to improve transparency and potentially reduce errors. The shop owner should consider implementing measures to diversify payment methods and improve data accuracy to mitigate the risks associated with relying on cash and transfers.
