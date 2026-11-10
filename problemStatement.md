# Facts-Only Mutual Fund FAQ Assistant

## Context

This project is a Retrieval-Augmented Generation (RAG) assistant for factual mutual fund questions, in the style of a Groww help experience. Retail investors and support teams ask the same scheme questions over and over: expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, and how to download a statement. The answers already exist in public documents from the asset management company (AMC), SEBI, AMFI, and Groww help pages. They are scattered across factsheets, scheme pages, and regulatory explainers.

A general-purpose chatbot is a poor fit. Scheme facts change, an unsourced number is not trustworthy, and a question that asks what to buy is investment advice. This assistant answers only from a curated corpus of official public sources, cites the page the fact came from, and refuses anything that is advice, opinion, or personal data.

## Objective

Design and implement an assistant that:

- Answers verifiable questions about a small, explicit set of mutual fund schemes
- Grounds every factual answer in text retrieved from the corpus
- Shows at least one source link and, when the corpus has it, the date that source was last captured
- Refuses investment advice, opinions, return predictions, and questions that include personal data
- Says clearly when the corpus does not contain the answer

## Scope

The first version covers HDFC Mutual Fund, using these five Groww scheme pages:

- [HDFC Mid Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth)
- [HDFC Small Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth)
- [HDFC Large Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth)
- [HDFC Silver ETF FoF Direct Growth](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth)
- [HDFC Multi Cap Fund Direct Growth](https://groww.in/mutual-funds/hdfc-multi-cap-fund-direct-growth)

The rest of the corpus is a curated set of public URLs alongside those scheme pages:

- AMC scheme pages, factsheets, and scheme information documents for the same five schemes
- SEBI and AMFI pages that define terms such as expense ratio, riskometer, and ELSS lock-in
- Groww help or learn articles for account actions such as downloading a capital gains statement or a consolidated account statement

Facts are only as current as the last time the corpus was refreshed. The assistant does not compute live NAV, historical returns, or the tax a specific investor owes.

## Questions it answers

The corpus is built for factual questions such as:

- What is the expense ratio of a named scheme?
- What is the exit load, and when does it apply?
- What is the minimum SIP or lump-sum amount?
- What is the ELSS lock-in period?
- What is the scheme’s riskometer level and benchmark?
- Who manages the scheme, and what is its investment objective?
- How does an investor download a capital gains statement or an account statement?

## Required behavior

### Factual answers

- Use only retrieved passages. Do not fill a gap from model memory.
- Keep the answer short and specific to the scheme named in the question.
- Include a citation URL from the corpus. When an AMC, SEBI, or AMFI page and a platform page both state the same fact, cite the official page.
- Include a “last updated from sources” date when the corpus records one.
- If retrieval finds nothing relevant, say the assistant does not have that information and point to where the user can look it up.

### Refusals

Reply with a short refusal and a pointer to investor education (AMFI, SEBI, or Groww learn) when the user asks for:

- A buy, sell, or hold recommendation, such as “Should I invest?”
- A ranking or comparison that asks which scheme is better
- Expected returns, outperformance, or market timing
- A portfolio, an allocation, or an amount they should invest
- Advice tied to their risk profile or tax situation

### Personal data

Do not accept or store identity or account secrets in the question. That includes PAN, Aadhaar, folio or account numbers, OTPs, email addresses, and phone numbers. Ask the user to remove that information and rephrase the factual question.

## System workflow

### 1. Corpus

Collect the public URLs. Record the source, document type, scheme, and access date. Store cleaned text for retrieval.

### 2. Index

Split each document into passages, embed the passages, and store them so a question can retrieve the passages that contain the fact.

### 3. Question handling

Classify the question before any answer is generated:

- Factual and in scope: retrieve passages, then write the answer from those passages
- Advice, opinion, or personal data: refuse, without calling the model for an answer
- Outside the chosen schemes, or absent from the corpus: say the information is not available

### 4. Response

Return a concise answer, the citation, and the corpus date. The interface states that the assistant shares public facts and does not give investment advice.

## What a reply contains

A factual reply includes:

- The answer in plain language
- The scheme it refers to
- At least one source link
- The date the source was last captured, when that date is known

A refusal states that the assistant only shares facts from public sources and points the user to official investor education.

## Success criteria

- Sample questions on expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, and statement downloads return answers that match the cited source
- Advice and “which is better” questions are refused
- Questions about schemes or facts outside the corpus are not answered with invented numbers
- A reader can open the citation and find the stated fact on that page
