import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Grid,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Alert,
  Skeleton
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  People,
  Recommend,
  Speed,
  Warning
} from '@mui/icons-material';

const SummaryCards = ({ experimentId }) => {
  const { data: summary, isLoading, error } = useQuery({
    queryKey: ['experiment-summary', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}/summary`);
      if (!response.ok) throw new Error('Failed to fetch experiment summary');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  if (isLoading) {
    return (
      <Grid container spacing={3}>
        {[1, 2, 3, 4].map((i) => (
          <Grid item xs={12} sm={6} md={3} key={i}>
            <Card>
              <CardContent>
                <Skeleton variant="text" width="60%" height={24} />
                <Skeleton variant="text" width="40%" height={32} />
                <Skeleton variant="text" width="80%" height={20} />
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 3 }}>
        Failed to load experiment summary: {error.message}
      </Alert>
    );
  }

  if (!summary) return null;

  const { traffic_split, active_users, serves, rewards, experiment } = summary;

  // Calculate traffic split percentage
  const totalUsers = traffic_split.reduce((sum, split) => sum + split.user_count, 0);
  const trafficSplitPercentage = traffic_split.reduce((acc, split) => {
    acc[split.policy] = split.percentage;
    return acc;
  }, {});

  // Get policy colors
  const getPolicyColor = (policy) => {
    const colors = {
      thompson: '#1976d2',
      egreedy: '#388e3c',
      ucb: '#f57c00',
      control: '#757575'
    };
    return colors[policy] || '#9e9e9e';
  };

  // Calculate trend indicators
  const getTrendIcon = (current, previous) => {
    if (current > previous) return <TrendingUp color="success" />;
    if (current < previous) return <TrendingDown color="error" />;
    return null;
  };

  return (
    <Grid container spacing={3}>
      {/* Traffic Split Card */}
      <Grid item xs={12} sm={6} md={3}>
        <Card>
          <CardHeader
            title={
              <Box display="flex" alignItems="center" gap={1}>
                <People color="primary" />
                <Typography variant="h6">Traffic Split</Typography>
              </Box>
            }
          />
          <CardContent>
            <Box mb={2}>
              {traffic_split.map((split) => (
                <Box key={split.policy} mb={1}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                    <Chip
                      label={split.policy}
                      size="small"
                      sx={{
                        backgroundColor: getPolicyColor(split.policy),
                        color: 'white',
                        fontWeight: 'bold'
                      }}
                    />
                    <Typography variant="body2" color="text.secondary">
                      {split.user_count.toLocaleString()} users
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={split.percentage}
                    sx={{
                      height: 8,
                      borderRadius: 4,
                      backgroundColor: 'rgba(0,0,0,0.1)',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: getPolicyColor(split.policy)
                      }
                    }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                    {split.percentage.toFixed(1)}%
                  </Typography>
                </Box>
              ))}
            </Box>
            <Typography variant="body2" color="text.secondary">
              Total: {totalUsers.toLocaleString()} users
            </Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Active Users Card */}
      <Grid item xs={12} sm={6} md={3}>
        <Card>
          <CardHeader
            title={
              <Box display="flex" alignItems="center" gap={1}>
                <People color="primary" />
                <Typography variant="h6">Active Users</Typography>
              </Box>
            }
          />
          <CardContent>
            <Box display="flex" alignItems="center" gap={1} mb={2}>
              <Typography variant="h4" color="primary">
                {active_users['24h'].toLocaleString()}
              </Typography>
              {getTrendIcon(active_users['24h'], active_users['7d'])}
            </Box>
            <Typography variant="body2" color="text.secondary" mb={1}>
              24 hours
            </Typography>
            <Typography variant="h6" color="text.secondary">
              {active_users['7d'].toLocaleString()} (7 days)
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {experiment.status === 'active' ? 'Live experiment' : 'Experiment ended'}
            </Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Total Serves Card */}
      <Grid item xs={12} sm={6} md={3}>
        <Card>
          <CardHeader
            title={
              <Box display="flex" alignItems="center" gap={1}>
                <Recommend color="primary" />
                <Typography variant="h6">Total Serves</Typography>
              </Box>
            }
          />
          <CardContent>
            <Typography variant="h4" color="primary" mb={2}>
              {serves.total.toLocaleString()}
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={1}>
              Recommendations served
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Since {new Date(experiment.start_at).toLocaleDateString()}
            </Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Mean Reward Card */}
      <Grid item xs={12} sm={6} md={3}>
        <Card>
          <CardHeader
            title={
              <Box display="flex" alignItems="center" gap={1}>
                <Speed color="primary" />
                <Typography variant="h6">Mean Reward</Typography>
              </Box>
            }
          />
          <CardContent>
            <Box display="flex" alignItems="center" gap={1} mb={2}>
              <Typography variant="h4" color="primary">
                {rewards.mean_24h.toFixed(3)}
              </Typography>
              {getTrendIcon(rewards.mean_24h, rewards.mean_7d)}
            </Box>
            <Typography variant="body2" color="text.secondary" mb={1}>
              24 hours
            </Typography>
            <Typography variant="h6" color="text.secondary">
              {rewards.mean_7d.toFixed(3)} (7 days)
            </Typography>
            {rewards.current_regret > 0 && (
              <Box mt={1}>
                <Chip
                  icon={<Warning />}
                  label={`Regret: ${rewards.current_regret.toFixed(3)}`}
                  color="warning"
                  size="small"
                />
              </Box>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

export default SummaryCards;
