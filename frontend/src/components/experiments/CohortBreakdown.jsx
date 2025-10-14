import React, { useState } from 'react';
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
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper
} from '@mui/material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Cell
} from 'recharts';
import {
  Refresh,
  TrendingUp,
  TrendingDown,
  Info,
  Warning
} from '@mui/icons-material';

const CohortBreakdown = ({ experimentId }) => {
  const [breakdown, setBreakdown] = useState('user_type');

  const { data: cohortData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-cohorts', experimentId, breakdown],
    queryFn: async () => {
      const response = await fetch(
        `/api/experiments/${experimentId}/cohorts?breakdown=${breakdown}`
      );
      if (!response.ok) throw new Error('Failed to fetch cohort data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

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

  // Process data for chart
  const processChartData = (data) => {
    if (!data) return [];

    const chartData = [];
    const cohorts = Object.keys(data);
    const policies = ['thompson', 'egreedy', 'ucb', 'control'];

    cohorts.forEach(cohort => {
      const cohortInfo = data[cohort];
      const chartItem = { cohort };
      
      policies.forEach(policy => {
        if (cohortInfo[policy]) {
          chartItem[policy] = cohortInfo[policy].reward_rate;
        } else {
          chartItem[policy] = 0;
        }
      });
      
      chartData.push(chartItem);
    });

    return chartData;
  };

  const chartData = processChartData(cohortData);

  // Calculate fairness metrics
  const calculateFairnessMetrics = (data) => {
    if (!data) return {};

    const fairness = {};
    const policies = ['thompson', 'egreedy', 'ucb', 'control'];

    policies.forEach(policy => {
      const policyRewards = [];
      Object.values(data).forEach(cohort => {
        if (cohort[policy]) {
          policyRewards.push(cohort[policy].reward_rate);
        }
      });

      if (policyRewards.length > 1) {
        const mean = policyRewards.reduce((sum, val) => sum + val, 0) / policyRewards.length;
        const variance = policyRewards.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / policyRewards.length;
        const stdDev = Math.sqrt(variance);
        const coefficientOfVariation = stdDev / mean;

        fairness[policy] = {
          mean,
          stdDev,
          coefficientOfVariation,
          isFair: coefficientOfVariation < 0.2 // Less than 20% variation is considered fair
        };
      }
    });

    return fairness;
  };

  const fairnessMetrics = calculateFairnessMetrics(cohortData);

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
            {label}
          </Typography>
          {payload.map((entry, index) => (
            <Box key={index} display="flex" alignItems="center" gap={1} mb={0.5}>
              <Box
                width={12}
                height={12}
                sx={{ backgroundColor: entry.color, borderRadius: '50%' }}
              />
              <Typography variant="body2">
                {entry.dataKey}: {entry.value?.toFixed(3) || 0}
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
        <CardHeader title="Cohort Breakdown" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Cohort Breakdown" />
        <CardContent>
          <Alert severity="error">
            Failed to load cohort data: {error.message}
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
            <Typography variant="h6">Cohort Breakdown</Typography>
            <Tooltip title="CTR breakdown by user type and fairness analysis">
              <IconButton size="small">
                <Info fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        }
        action={
          <Box display="flex" alignItems="center" gap={2}>
            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel>Breakdown</InputLabel>
              <Select
                value={breakdown}
                label="Breakdown"
                onChange={(e) => setBreakdown(e.target.value)}
              >
                <MenuItem value="user_type">User Type</MenuItem>
                <MenuItem value="time_period">Time Period</MenuItem>
              </Select>
            </FormControl>
            <IconButton onClick={() => refetch()} size="small">
              <Refresh />
            </IconButton>
          </Box>
        }
      />
      <CardContent>
        {/* Fairness Alerts */}
        {Object.entries(fairnessMetrics).map(([policy, metrics]) => (
          !metrics.isFair && (
            <Alert
              key={policy}
              severity="warning"
              sx={{ mb: 2 }}
              icon={<Warning />}
            >
              <Typography variant="body2">
                <strong>{policy.charAt(0).toUpperCase() + policy.slice(1)}</strong> shows 
                high variance across cohorts (CV: {metrics.coefficientOfVariation.toFixed(2)}). 
                Consider investigating fairness issues.
              </Typography>
            </Alert>
          )
        ))}

        {/* Chart */}
        <Box height={400} mb={3}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="cohort"
                tickFormatter={(value) => value.replace('_', ' ').toUpperCase()}
                stroke="#666"
              />
              <YAxis
                label={{ value: 'Reward Rate', angle: -90, position: 'insideLeft' }}
                stroke="#666"
              />
              <RechartsTooltip content={<CustomTooltip />} />
              <Legend />
              
              <Bar dataKey="thompson" fill={getPolicyColor('thompson')} name="Thompson" />
              <Bar dataKey="egreedy" fill={getPolicyColor('egreedy')} name="ε-greedy" />
              <Bar dataKey="ucb" fill={getPolicyColor('ucb')} name="UCB1" />
              <Bar dataKey="control" fill={getPolicyColor('control')} name="Control" />
            </BarChart>
          </ResponsiveContainer>
        </Box>

        {/* Detailed Table */}
        <Typography variant="subtitle2" gutterBottom>
          Detailed Cohort Performance
        </Typography>
        <TableContainer component={Paper} sx={{ maxHeight: 300 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Cohort</TableCell>
                <TableCell align="center">Thompson</TableCell>
                <TableCell align="center">ε-greedy</TableCell>
                <TableCell align="center">UCB1</TableCell>
                <TableCell align="center">Control</TableCell>
                <TableCell align="center">Best Policy</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Object.entries(cohortData || {}).map(([cohort, policies]) => {
                const policyRewards = Object.entries(policies).map(([policy, data]) => ({
                  policy,
                  reward: data.reward_rate,
                  events: data.events
                }));
                
                const bestPolicy = policyRewards.reduce((best, current) => 
                  current.reward > best.reward ? current : best
                );

                return (
                  <TableRow key={cohort}>
                    <TableCell>
                      <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                        {cohort.replace('_', ' ')}
                      </Typography>
                    </TableCell>
                    {['thompson', 'egreedy', 'ucb', 'control'].map(policy => {
                      const policyData = policies[policy];
                      const isBest = policy === bestPolicy.policy;
                      
                      return (
                        <TableCell key={policy} align="center">
                          <Box display="flex" flexDirection="column" alignItems="center">
                            <Typography
                              variant="body2"
                              fontWeight={isBest ? 'bold' : 'normal'}
                              color={isBest ? 'primary' : 'text.primary'}
                            >
                              {policyData ? policyData.reward_rate.toFixed(3) : 'N/A'}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              ({policyData ? policyData.events.toLocaleString() : 0} events)
                            </Typography>
                          </Box>
                        </TableCell>
                      );
                    })}
                    <TableCell align="center">
                      <Chip
                        label={bestPolicy.policy}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Fairness Summary */}
        <Box mt={3} p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
          <Typography variant="subtitle2" gutterBottom>
            Fairness Analysis
          </Typography>
          <Box display="flex" gap={3} flexWrap="wrap">
            {Object.entries(fairnessMetrics).map(([policy, metrics]) => (
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
                  CV {metrics.coefficientOfVariation.toFixed(2)}
                </Typography>
                {metrics.isFair ? (
                  <TrendingUp fontSize="small" color="success" />
                ) : (
                  <TrendingDown fontSize="small" color="warning" />
                )}
                <Typography variant="caption" color="text.secondary">
                  ({metrics.isFair ? 'Fair' : 'Unfair'})
                </Typography>
              </Box>
            ))}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Coefficient of Variation (CV) measures fairness across cohorts. 
            CV &lt; 0.2 indicates fair treatment across user segments.
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default CohortBreakdown;
