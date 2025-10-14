import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Alert,
  Skeleton,
  Tooltip,
  IconButton
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import {
  Refresh,
  TrendingUp,
  TrendingDown,
  Info
} from '@mui/icons-material';

const RewardChart = ({ experimentId }) => {
  const [granularity, setGranularity] = useState('hour');
  const [selectedPolicies, setSelectedPolicies] = useState(['thompson', 'egreedy', 'ucb']);

  const { data: timeseriesData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-timeseries', experimentId, granularity],
    queryFn: async () => {
      const response = await fetch(
        `/api/experiments/${experimentId}/timeseries?metric=reward&granularity=${granularity}`
      );
      if (!response.ok) throw new Error('Failed to fetch timeseries data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  const { data: summaryData } = useQuery({
    queryKey: ['experiment-summary', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}/summary`);
      if (!response.ok) throw new Error('Failed to fetch experiment summary');
      return response.json();
    },
    enabled: !!experimentId
  });

  // Process data for chart
  const processChartData = (data) => {
    if (!data) return [];

    // Group data by timestamp and policy
    const groupedData = {};
    
    data.forEach(item => {
      const timestamp = item.timestamp;
      if (!groupedData[timestamp]) {
        groupedData[timestamp] = { timestamp };
      }
      groupedData[timestamp][item.policy] = item.value;
    });

    // Convert to array and sort by timestamp
    return Object.values(groupedData)
      .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  };

  const chartData = processChartData(timeseriesData);

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

  // Calculate cumulative rewards
  const calculateCumulativeRewards = (data) => {
    const cumulative = {};
    const policies = ['thompson', 'egreedy', 'ucb', 'control'];
    
    policies.forEach(policy => {
      cumulative[policy] = 0;
    });

    return data.map(item => {
      const result = { ...item };
      policies.forEach(policy => {
        if (item[policy] !== undefined) {
          cumulative[policy] += item[policy];
          result[`${policy}_cumulative`] = cumulative[policy];
        }
      });
      return result;
    });
  };

  const cumulativeData = calculateCumulativeRewards(chartData);

  // Calculate trend for each policy
  const calculateTrend = (policy) => {
    if (cumulativeData.length < 2) return 0;
    
    const firstValue = cumulativeData[0][`${policy}_cumulative`] || 0;
    const lastValue = cumulativeData[cumulativeData.length - 1][`${policy}_cumulative`] || 0;
    
    return lastValue - firstValue;
  };

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Box
          sx={{
            backgroundColor: 'white',
            border: '1px solid #ccc',
            borderRadius: 1,
            p: 2,
            boxShadow: 2
          }}
        >
          <Typography variant="body2" color="text.secondary" mb={1}>
            {new Date(label).toLocaleString()}
          </Typography>
          {payload.map((entry, index) => (
            <Box key={index} display="flex" alignItems="center" gap={1} mb={0.5}>
              <Box
                width={12}
                height={12}
                sx={{ backgroundColor: entry.color, borderRadius: '50%' }}
              />
              <Typography variant="body2">
                {entry.dataKey.replace('_cumulative', '')}: {entry.value?.toFixed(3) || 0}
              </Typography>
            </Box>
          ))}
        </Box>
      );
    }
    return null;
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Reward Trends" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Reward Trends" />
        <CardContent>
          <Alert severity="error">
            Failed to load reward data: {error.message}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title={
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="h6">Reward Trends</Typography>
            <Tooltip title="Cumulative reward over time for each policy">
              <IconButton size="small">
                <Info fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        }
        action={
          <Box display="flex" alignItems="center" gap={2}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Granularity</InputLabel>
              <Select
                value={granularity}
                label="Granularity"
                onChange={(e) => setGranularity(e.target.value)}
              >
                <MenuItem value="hour">Hour</MenuItem>
                <MenuItem value="day">Day</MenuItem>
              </Select>
            </FormControl>
            <IconButton onClick={() => refetch()} size="small">
              <Refresh />
            </IconButton>
          </Box>
        }
      />
      <CardContent>
        {/* Policy Legend with Trends */}
        <Box display="flex" gap={2} mb={3} flexWrap="wrap">
          {['thompson', 'egreedy', 'ucb'].map(policy => {
            const trend = calculateTrend(policy);
            const isSelected = selectedPolicies.includes(policy);
            
            return (
              <Chip
                key={policy}
                label={
                  <Box display="flex" alignItems="center" gap={1}>
                    <Box
                      width={12}
                      height={12}
                      sx={{ backgroundColor: getPolicyColor(policy), borderRadius: '50%' }}
                    />
                    <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                      {policy}
                    </Typography>
                    {trend > 0 && <TrendingUp fontSize="small" color="success" />}
                    {trend < 0 && <TrendingDown fontSize="small" color="error" />}
                    <Typography variant="caption" color="text.secondary">
                      ({trend.toFixed(1)})
                    </Typography>
                  </Box>
                }
                onClick={() => {
                  if (isSelected) {
                    setSelectedPolicies(prev => prev.filter(p => p !== policy));
                  } else {
                    setSelectedPolicies(prev => [...prev, policy]);
                  }
                }}
                variant={isSelected ? "filled" : "outlined"}
                sx={{
                  backgroundColor: isSelected ? getPolicyColor(policy) : 'transparent',
                  color: isSelected ? 'white' : getPolicyColor(policy),
                  borderColor: getPolicyColor(policy),
                  '&:hover': {
                    backgroundColor: isSelected ? getPolicyColor(policy) : `${getPolicyColor(policy)}20`
                  }
                }}
              />
            );
          })}
        </Box>

        {/* Chart */}
        <Box height={400}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={cumulativeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={(value) => new Date(value).toLocaleTimeString()}
                stroke="#666"
              />
              <YAxis
                label={{ value: 'Cumulative Reward', angle: -90, position: 'insideLeft' }}
                stroke="#666"
              />
              <RechartsTooltip content={<CustomTooltip />} />
              <Legend />
              
              {/* Policy Lines */}
              {selectedPolicies.map(policy => (
                <Line
                  key={policy}
                  type="monotone"
                  dataKey={`${policy}_cumulative`}
                  stroke={getPolicyColor(policy)}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name={policy.charAt(0).toUpperCase() + policy.slice(1)}
                />
              ))}
              
              {/* Reference line for target reward */}
              {summaryData?.rewards?.mean_7d && (
                <ReferenceLine
                  y={summaryData.rewards.mean_7d * cumulativeData.length}
                  stroke="#ff9800"
                  strokeDasharray="5 5"
                  label={{ value: "7-day Average", position: "topRight" }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </Box>

        {/* Summary Stats */}
        <Box mt={3} p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
          <Typography variant="subtitle2" gutterBottom>
            Current Performance (Last 24h)
          </Typography>
          <Box display="flex" gap={3} flexWrap="wrap">
            {selectedPolicies.map(policy => {
              const lastDataPoint = cumulativeData[cumulativeData.length - 1];
              const currentReward = lastDataPoint?.[`${policy}_cumulative`] || 0;
              const previousReward = cumulativeData[cumulativeData.length - 2]?.[`${policy}_cumulative`] || 0;
              const change = currentReward - previousReward;
              
              return (
                <Box key={policy} display="flex" alignItems="center" gap={1}>
                  <Box
                    width={8}
                    height={8}
                    sx={{ backgroundColor: getPolicyColor(policy), borderRadius: '50%' }}
                  />
                  <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                    {policy}:
                  </Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {currentReward.toFixed(1)}
                  </Typography>
                  {change > 0 && <TrendingUp fontSize="small" color="success" />}
                  {change < 0 && <TrendingDown fontSize="small" color="error" />}
                  <Typography variant="caption" color="text.secondary">
                    ({change > 0 ? '+' : ''}{change.toFixed(1)})
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

export default RewardChart;
