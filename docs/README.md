# Movie Recommender Pipeline

A Python pipeline for fetching movie data from The Movie Database (TMDB) API and storing it in a database.

## Setup

1. **Create and activate virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get TMDB API Key:**
   - Visit [TMDB API Settings](https://www.themoviedb.org/settings/api)
   - Create a free account and request an API key
   - Set your API key as an environment variable:
     ```bash
     export TMDB_API_KEY="your_api_key_here"
     ```

## Usage

### Basic Usage

```python
from pipeline import MoviePipeline

# Initialize pipeline with your API key
pipeline = MoviePipeline("your_api_key_here")

# Extract movies (fetches 5 pages by default)
movies = pipeline.extract()

# Transform data into a clean DataFrame
df = pipeline.transform(movies)

# Load data into database
pipeline.load(df, "sqlite:///movies.db")
```

### Testing

Run the test script to verify everything works:

```bash
source venv/bin/activate
python test_pipeline.py
```

## Features

- **Extract**: Fetches popular movies from TMDB API
- **Transform**: Cleans and structures the data into a pandas DataFrame
- **Load**: Stores the data in a SQL database

## Data Schema

The pipeline extracts the following movie fields:
- `id`: TMDB movie ID
- `title`: Movie title
- `overview`: Movie description
- `release_date`: Release date
- `vote_average`: Average rating
- `genre_ids`: List of genre IDs
- `poster_path`: Poster image path
- `poster_url`: Full poster URL
