# hugo-posse

A Python utility that automatically syndicates [Hugo](https://gohugo.io) blog posts to **Bluesky** and **Mastodon**.

It implements the [POSSE](https://indieweb.org/POSSE) (Publish on Own Site, Syndicate Elsewhere) philosophy by parsing your local front matter and posting to social platforms (Bluesky, Mastodon) only when you tell it to.

Here are some blogposts dicussing the theory and how I use the script:
* [POSSE for Hugo Part 1 - Theory](https://www.kevinrkuhl.com/blog/2025/12/posse-for-hugo-part-one-theory/)
* [POSSE for Hugo Part 2 - The Product](https://www.kevinrkuhl.com/blog/2025/12/posse-for-hugo-pt2/)

## Features

* **Safe Syndication:** Checks your live site for a `200 OK` response before posting (prevents broken links).
* **Avoids duplicates:** Marks posts as `syndicated: true`/`syndicated = true` in your front matter to prevent duplicate posts.
* **Format Agnostic:** Handles both TOML (`+++`) and YAML (`---`) front matter.
* **Dry Run Mode:** Preview exactly what will happen without sending data to APIs.

## Prerequisites

* Python 3.11+ (Required for `tomllib`)
* Hugo

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/kevinrkuhl/hugo-posse.git
    cd hugo-posse
    ```

2. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Update your `.gitignore` to include `.env` files. This is essential for protecting your credentials for Bluesky and Mastodon. I recommend the following lines:

    ```text
    .env
    __pycache__/
    *.pyc
    ```

4. Set up your environment:

    ```bash
    cp .env.example .env
    ```

    Open the `.env` file and add the URL for your site.

5. Configure Bluesky and Mastodon connections:
    1. For Bluesky:
        1. Log in, and add your Bluesky handle (e.g., username.bsky.social) to your `.env` as the `BSKY_HANDLE`.
        2. Navigate to your settings (gear icon), then select **Privacy and Security** > **App passwords**.
        3. Press **+Add App Password**.
        4. Enter a name for the app password, and select **Next**.
        5. Copy the app password into your `.env` as the `BSKY_PASSWORD`.
        6. Save your `.env`.
        7. In Bluesky, press **Done**. You won't be able to see the app password again.
    2. For Mastodon:
        1. Log in and note the base url for your federated instance (e.g., `mastodon.social`)
        2. Navigate to preferences (gear icon), then **Development**.
        3. Press **New application**.
        4. Enter a name for your application (e.g., `HugoPOSSE`).
        5. Check the `write:statuses` permission.
        6. Submit.
        7. Select your new application from the list of applications and copy the access token. Add this as the `MASTODON_ACCESS_TOKEN` value in your `.env`.
        8. Save your `.env`.

This configuration is recommended if you want to update the script from this project. Alternately, copy and paste `posse.py` to your site root, and update your `.gitignore` and `.env` files manually.

## Usage

### 1. Prepare your post

Add the following fields to your post's front matter:

```yaml
syndicate_to: ["bluesky", "mastodon"]
microblog_content: "This is the text that will appear on social media. 🤖"
```

### 2. Run the script

Navigate into the hugo-posse directory and run the script:

```bash
python posse.py ../content/posts
```

This is a full "live run" that will crawl for posts with syndication front matter, attempt to create Bluesky/Mastodon clients, then generate posts.

### 3. Options

`--dry-run`: Scans files and simulates the process without hitting APIs or modifying files.

```bash
python posse.py ../content/blog --dry-run
```

`--force`: Skips the URL verification check (useful if you are testing locally or know the URL is valid).

## Future updates

Some ideas for extending this utility include:

* An option for front matter that includes "no-sharing link" argument. This lets you single-source posts to multiple social networks.
* Content sharing mode to cross post shared links.
* Additional target social networks (LinkedIn, Twitter/X).
* Support for other SSGs and Obsidian.

Feel free to modify it to support your environment!

## Known issues

* The script will fail to parse front matter if it the delimiter is not the first line in your file. I'll be workign on a fix for this shortly.
* Bluesky handles hashtags as metadata, so I plan on adding a method to parse and extract hashtags for Bluesky.

## License

This project is available under the MIT license.
