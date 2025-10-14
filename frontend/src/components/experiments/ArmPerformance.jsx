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
  Paper,
  TableSortLabel,
  TextField,
  InputAdornment,
  Badge
} from '@mui/material';
import {
  Refresh,
  TrendingUp,
  TrendingDown,
  Info,
  Warning,
  Search,
  Star,
  StarBorder
} from '@mui/icons-material';

const ArmPerformance = ({ experimentId }) => {
  const [sortBy, setSortBy] = useState('reward_rate');
  const [limit, setLimit] = useState(20);
  const [policy, setPolicy] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [favorites, setFavorites] = useState(new Set());

  const { data: armData, isLoading, error, refetch } = useQuery({
    queryKey: ['experiment-arms', experimentId, sortBy, limit, policy],
    queryFn: async () => {
      const params = new URLSearchParams({
        sort: sortBy,
        limit: limit.toString()
      });
      if (policy) params.append('policy', policy);
      
      const response = await fetch(
        `/api/experiments/${experimentId}/arms?${params}`
      );
      if (!response.ok) throw new Error('Failed to fetch arm performance data');
      return response.json();
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    enabled: !!experimentId
  });

  // Filter and search arms
  const filteredArms = armData?.filter(arm => 
    arm.arm_id.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

  // Calculate anomaly detection
  const detectAnomalies = (arms) => {
    if (!arms || arms.length === 0) return {};

    const anomalies = {};
    
    // Calculate thresholds
    const serves = arms.map(arm => arm.serves);
    const rewardRates = arms.map(arm => arm.reward_rate);
    
    const serveMean = serves.reduce((sum, val) => sum + val, 0) / serves.length;
    const serveStd = Math.sqrt(serves.reduce((sum, val) => sum + Math.pow(val - serveMean, 2), 0) / serves.length);
    
    const rewardMean = rewardRates.reduce((sum, val) => sum + val, 0) / rewardRates.length;
    const rewardStd = Math.sqrt(rewardRates.reduce((sum, val) => sum + Math.pow(val - rewardMean, 2), 0) / rewardRates.length);

    arms.forEach(arm => {
      const anomalies_list = [];
      
      // High serves, low reward (over-exploration)
      if (arm.serves > serveMean + 2 * serveStd && arm.reward_rate < rewardMean - rewardStd) {
        anomalies_list.push('over-exploration');
      }
      
      // Low serves, high reward (under-exploration)
      if (arm.serves < serveMean - serveStd && arm.reward_rate > rewardMean + rewardStd) {
        anomalies_list.push('under-exploration');
      }
      
      // High latency
      if (arm.avg_latency > 100) {
        anomalies_list.push('high-latency');
      }
      
      // High regret
      if (arm.regret > 0.1) {
        anomalies_list.push('high-regret');
      }
      
      if (anomalies_list.length > 0) {
        anomalies[arm.arm_id] = anomalies_list;
      }
    });

    return anomalies;
  };

  const anomalies = detectAnomalies(filteredArms);

  // Get anomaly color
  const getAnomalyColor = (anomalyType) => {
    const colors = {
      'over-exploration': 'warning',
      'under-exploration': 'info',
      'high-latency': 'error',
      'high-regret': 'error'
    };
    return colors[anomalyType] || 'default';
  };

  // Get anomaly icon
  const getAnomalyIcon = (anomalyType) => {
    const icons = {
      'over-exploration': <TrendingDown />,
      'under-exploration': <TrendingUp />,
      'high-latency': <Warning />,
      'high-regret': <Warning />
    };
    return icons[anomalyType] || <Info />;
  };

  // Toggle favorite
  const toggleFavorite = (armId) => {
    const newFavorites = new Set(favorites);
    if (newFavorites.has(armId)) {
      newFavorites.delete(armId);
    } else {
      newFavorites.add(armId);
    }
    setFavorites(newFavorites);
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Arm Performance" />
        <CardContent>
          <Skeleton variant="rectangular" height={400} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader title="Arm Performance" />
        <CardContent>
          <Alert severity="error">
            Failed to load arm performance data: {error.message}
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
            <Typography variant="h6">Arm Performance</Typography>
            <Tooltip title="Performance metrics and anomaly detection for each arm">
              <IconButton size="small">
                <Info fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        }
        action={
          <Box display="flex" alignItems="center" gap={2}>
            <TextField
              size="small"
              placeholder="Search arms..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 200 }}
            />
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Policy</InputLabel>
              <Select
                value={policy}
                label="Policy"
                onChange={(e) => setPolicy(e.target.value)}
              >
                <MenuItem value="">All Policies</MenuItem>
                <MenuItem value="thompson">Thompson</MenuItem>
                <MenuItem value="egreedy">ε-greedy</MenuItem>
                <MenuItem value="ucb">UCB1</MenuItem>
                <MenuItem value="control">Control</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 100 }}>
              <InputLabel>Limit</InputLabel>
              <Select
                value={limit}
                label="Limit"
                onChange={(e) => setLimit(e.target.value)}
              >
                <MenuItem value={10}>10</MenuItem>
                <MenuItem value={20}>20</MenuItem>
                <MenuItem value={50}>50</MenuItem>
                <MenuItem value={100}>100</MenuItem>
              </Select>
            </FormControl>
            <IconButton onClick={() => refetch()} size="small">
              <Refresh />
            </IconButton>
          </Box>
        }
      />
      <CardContent>
        {/* Anomaly Summary */}
        {Object.keys(anomalies).length > 0 && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Typography variant="body2">
              <strong>{Object.keys(anomalies).length}</strong> arms detected with anomalies. 
              Review the highlighted rows below.
            </Typography>
          </Alert>
        )}

        {/* Performance Table */}
        <TableContainer component={Paper} sx={{ maxHeight: 600 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>
                  <TableSortLabel
                    active={sortBy === 'arm_id'}
                    direction={sortBy === 'arm_id' ? 'asc' : 'asc'}
                    onClick={() => setSortBy('arm_id')}
                  >
                    Arm ID
                  </TableSortLabel>
                </TableCell>
                <TableCell align="center">
                  <TableSortLabel
                    active={sortBy === 'serves'}
                    direction={sortBy === 'serves' ? 'desc' : 'asc'}
                    onClick={() => setSortBy('serves')}
                  >
                    Serves
                  </TableSortLabel>
                </TableCell>
                <TableCell align="center">
                  <TableSortLabel
                    active={sortBy === 'reward_rate'}
                    direction={sortBy === 'reward_rate' ? 'desc' : 'asc'}
                    onClick={() => setSortBy('reward_rate')}
                  >
                    Reward Rate
                  </TableSortLabel>
                </TableCell>
                <TableCell align="center">
                  <TableSortLabel
                    active={sortBy === 'regret'}
                    direction={sortBy === 'regret' ? 'asc' : 'asc'}
                    onClick={() => setSortBy('regret')}
                  >
                    Regret
                  </TableSortLabel>
                </TableCell>
                <TableCell align="center">Avg Latency</TableCell>
                <TableCell align="center">Unique Users</TableCell>
                <TableCell align="center">Anomalies</TableCell>
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredArms.map((arm, index) => {
                const armAnomalies = anomalies[arm.arm_id] || [];
                const isFavorite = favorites.has(arm.arm_id);
                
                return (
                  <TableRow 
                    key={arm.arm_id}
                    sx={{
                      backgroundColor: armAnomalies.length > 0 ? 'rgba(255, 152, 0, 0.1)' : 'inherit',
                      '&:hover': {
                        backgroundColor: armAnomalies.length > 0 ? 'rgba(255, 152, 0, 0.2)' : 'rgba(0, 0, 0, 0.04)'
                      }
                    }}
                  >
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="body2" fontWeight="bold">
                          {arm.arm_id}
                        </Typography>
                        {index < 3 && (
                          <Chip
                            label={`#${index + 1}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {arm.serves.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Box display="flex" alignItems="center" justifyContent="center" gap={1}>
                        <Typography variant="body2" fontWeight="bold">
                          {arm.reward_rate.toFixed(3)}
                        </Typography>
                        {arm.reward_rate > 0.5 && <TrendingUp fontSize="small" color="success" />}
                        {arm.reward_rate < 0.2 && <TrendingDown fontSize="small" color="error" />}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Typography 
                        variant="body2"
                        color={arm.regret > 0.1 ? 'error' : 'text.primary'}
                        fontWeight={arm.regret > 0.1 ? 'bold' : 'normal'}
                      >
                        {arm.regret.toFixed(3)}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography 
                        variant="body2"
                        color={arm.avg_latency > 100 ? 'error' : 'text.primary'}
                      >
                        {arm.avg_latency.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2">
                        {arm.unique_users.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Box display="flex" gap={0.5} flexWrap="wrap" justifyContent="center">
                        {armAnomalies.map((anomaly, idx) => (
                          <Tooltip key={idx} title={anomaly.replace('-', ' ')}>
                            <Chip
                              icon={getAnomalyIcon(anomaly)}
                              label=""
                              size="small"
                              color={getAnomalyColor(anomaly)}
                              variant="outlined"
                            />
                          </Tooltip>
                        ))}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <IconButton
                        size="small"
                        onClick={() => toggleFavorite(arm.arm_id)}
                        color={isFavorite ? 'primary' : 'default'}
                      >
                        {isFavorite ? <Star /> : <StarBorder />}
                      </IconButton>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>

        {/* Summary Stats */}
        <Box mt={3} p={2} sx={{ backgroundColor: 'grey.50', borderRadius: 1 }}>
          <Typography variant="subtitle2" gutterBottom>
            Performance Summary
          </Typography>
          <Box display="flex" gap={3} flexWrap="wrap">
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="body2">Total Arms:</Typography>
              <Typography variant="body2" fontWeight="bold">
                {filteredArms.length}
              </Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="body2">Anomalies:</Typography>
              <Typography variant="body2" fontWeight="bold" color="warning.main">
                {Object.keys(anomalies).length}
              </Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="body2">Avg Reward Rate:</Typography>
              <Typography variant="body2" fontWeight="bold">
                {(filteredArms.reduce((sum, arm) => sum + arm.reward_rate, 0) / filteredArms.length).toFixed(3)}
              </Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="body2">Favorites:</Typography>
              <Typography variant="body2" fontWeight="bold">
                {favorites.size}
              </Typography>
            </Box>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ArmPerformance;
