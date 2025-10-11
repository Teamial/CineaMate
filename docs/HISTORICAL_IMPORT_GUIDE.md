# Historical Movie Import System - Usage Guide

## 🎬 Overview

The historical movie import system allows you to import thousands of movies from TMDB with batch processing to avoid API rate limits and scheduled updates for continuous growth.

## 📁 Files Created

1. **`historical_movie_import.py`** - Main import script with batch processing
2. **`monitor_database.py`** - Database monitoring and progress tracking
3. **`test_historical_import.py`** - Test script to verify functionality
4. **`backend/scheduler.py`** - Updated with historical import jobs

## 🚀 Quick Start

### 1. Test the System

```bash
cd /Users/tea/Documents/Passion-Projects/movie_recommender
python test_historical_import.py
```

### 2. Import Recent Movies (Last 30 Days)

```bash
python historical_movie_import.py --recent-only --days-back 30
```

### 3. Import Historical Movies (2020-2024)

```bash
python historical_movie_import.py --start-year 2020 --end-year 2024 --pages-per-year 10
```

### 4. Monitor Progress

```bash
python monitor_database.py --status
```

## 📊 Expected Results

### Small Test (2023-2024, 5 pages each)
- **Movies**: ~200-400 movies
- **Time**: 5-10 minutes
- **Storage**: ~1-2 MB

### Medium Import (2020-2024, 10 pages each)
- **Movies**: ~2,000-4,000 movies
- **Time**: 30-60 minutes
- **Storage**: ~10-20 MB

### Large Import (1990-2024, 20 pages each)
- **Movies**: ~10,000-20,000 movies
- **Time**: 3-6 hours
- **Storage**: ~50-100 MB

## ⚙️ Configuration Options

### Historical Import Script

```bash
python historical_movie_import.py [OPTIONS]

Options:
  --start-year YEAR        Starting year (default: 1990)
  --end-year YEAR          Ending year (default: 2024)
  --pages-per-year PAGES   Pages per year (default: 20)
  --batch-years YEARS      Years per batch (default: 5)
  --recent-only            Import only recent movies
  --days-back DAYS         Days back for recent import (default: 30)
```

### Monitoring Script

```bash
python monitor_database.py [OPTIONS]

Options:
  --status                 Show current database status
  --monitor                Monitor growth over time
  --interval MINUTES       Monitoring interval (default: 60)
  --duration HOURS         Monitoring duration (default: 24)
  --estimate TARGET        Estimate time to reach target count
```

## 🔄 Scheduled Updates

The scheduler now includes:

1. **Historical Recent Update**: Every Monday at 1 AM
   - Imports movies from last 30 days
   - ~100-300 movies per run

2. **Historical Batch Import**: First Sunday of month at 12 AM
   - Imports 5 years of movies
   - ~1,500-3,000 movies per run

3. **Existing Jobs**:
   - Quick update: Every 6 hours
   - Daily update: Every day at 3 AM
   - Weekly enrichment: Every Sunday at 2 AM
   - Embedding refresh: Every day at 4 AM

## 📈 Monitoring & Analytics

### Database Status

```bash
python monitor_database.py --status
```

Shows:
- Total movies count
- Embedding coverage
- Enrichment coverage
- Recent activity (24h, 7d, 30d)
- Top genres and years
- Pipeline run history

### Growth Monitoring

```bash
python monitor_database.py --monitor --interval 30 --duration 12
```

Monitors database growth for 12 hours, checking every 30 minutes.

### Completion Estimation

```bash
python monitor_database.py --estimate 10000
```

Estimates how long it will take to reach 10,000 movies based on recent growth.

## 🎯 Batch Processing Features

### API Rate Limiting
- **Delay**: 0.3 seconds between API calls
- **Batch delay**: 5 seconds between year batches
- **Respects TMDB limits**: 40 requests per 10 seconds

### Error Handling
- **Retry logic**: Failed requests are logged but don't stop the process
- **Graceful degradation**: Continues with partial data if some requests fail
- **Progress tracking**: Shows real-time progress and statistics

### Memory Management
- **Batch processing**: Processes years in small batches
- **Duplicate removal**: Automatically removes duplicate movies
- **Incremental updates**: Uses upsert to avoid duplicates

## 🔧 Manual Scheduler Control

### Start Scheduler

```bash
# Via API
curl -X POST http://localhost:8000/pipeline/scheduler/start \
  -H "Authorization: Bearer YOUR_TOKEN"

# Via Python
python -c "
from backend.scheduler import get_scheduler
scheduler = get_scheduler()
scheduler.start()
"
```

### Manual Historical Import

```bash
# Via API
curl -X POST http://localhost:8000/pipeline/run \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"update_type": "historical_recent"}'

# Via Python
python -c "
from backend.scheduler import get_scheduler
scheduler = get_scheduler()
scheduler.run_manual_update('historical_recent')
"
```

## 📊 Performance Optimization

### For Large Imports

1. **Increase batch size**:
   ```python
   # In historical_movie_import.py
   self.batch_delay = 3  # Reduce from 5 to 3 seconds
   ```

2. **Adjust API delay**:
   ```python
   # In historical_movie_import.py
   self.api_delay = 0.2  # Reduce from 0.3 to 0.2 seconds
   ```

3. **Use more pages per year**:
   ```bash
   python historical_movie_import.py --pages-per-year 25
   ```

### For Small Imports

1. **Reduce batch size**:
   ```bash
   python historical_movie_import.py --batch-years 2
   ```

2. **Focus on recent years**:
   ```bash
   python historical_movie_import.py --start-year 2020
   ```

## 🐛 Troubleshooting

### Common Issues

1. **API Rate Limit Errors**
   - Increase `api_delay` in the script
   - Reduce `pages_per_year`
   - Use smaller `batch_years`

2. **Database Connection Errors**
   - Check `DATABASE_URL` in `.env`
   - Ensure PostgreSQL is running
   - Verify database permissions

3. **Memory Issues**
   - Reduce `pages_per_year`
   - Use smaller `batch_years`
   - Process fewer years at once

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python historical_movie_import.py --start-year 2023 --end-year 2024
```

## 📈 Expected Growth Timeline

### Week 1
- **Movies**: 2,000-5,000
- **Sources**: Recent + small historical batch

### Month 1
- **Movies**: 10,000-20,000
- **Sources**: Multiple historical batches + scheduled updates

### Month 3
- **Movies**: 30,000-50,000
- **Sources**: Full historical coverage + continuous updates

## 🎉 Success Metrics

- **Import Success Rate**: >95%
- **API Error Rate**: <5%
- **Database Growth**: Consistent daily additions
- **Embedding Coverage**: >90%
- **Enrichment Coverage**: >80%

## 📞 Support

For issues or questions:

1. **Check logs**: Look for error messages in the output
2. **Run tests**: `python test_historical_import.py`
3. **Monitor status**: `python monitor_database.py --status`
4. **Check scheduler**: Verify scheduled jobs are running

---

**Total Implementation**: ~1,000 lines of code  
**Setup Time**: ~10 minutes  
**Breaking Changes**: None (fully backward compatible)  
**Performance Impact**: Positive (automated growth)
