import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Container,
  Grid,
  Paper,
  Tabs,
  Tab,
  Alert,
  Skeleton,
  IconButton,
  Tooltip,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  Divider
} from '@mui/material';
import {
  ArrowBack,
  Refresh,
  Info,
  Warning,
  CheckCircle,
  Error,
  TrendingUp,
  TrendingDown,
  Speed,
  People,
  Recommend,
  Security
} from '@mui/icons-material';

// Import dashboard components
import SummaryCards from '../components/experiments/SummaryCards';
import RewardChart from '../components/experiments/RewardChart';
import CohortBreakdown from '../components/experiments/CohortBreakdown';
import ArmPerformance from '../components/experiments/ArmPerformance';
import LatencyDistribution from '../components/experiments/LatencyDistribution';
import EventLog from '../components/experiments/EventLog';
import GuardrailStatus from '../components/experiments/GuardrailStatus';

const ExperimentDashboard = () => {
  const { id: experimentId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState(0);
  const [infoDialogOpen, setInfoDialogOpen] = useState(false);

  // Fetch experiment details
  const { data: experimentData, isLoading, error } = useQuery({
    queryKey: ['experiment-details', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}`);
      if (!response.ok) throw new Error('Failed to fetch experiment details');
      return response.json();
    },
    enabled: !!experimentId
  });

  // Fetch experiment summary for quick stats
  const { data: summaryData } = useQuery({
    queryKey: ['experiment-summary', experimentId],
    queryFn: async () => {
      const response = await fetch(`/api/experiments/${experimentId}/summary`);
      if (!response.ok) throw new Error('Failed to fetch experiment summary');
      return response.json();
    },
    enabled: !!experimentId
  });

  // Handle tab change
  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  // Get experiment status color
  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
        return 'success';
      case 'ended':
        return 'default';
      case 'paused':
        return 'warning';
      default:
        return 'default';
    }
  };

  // Get experiment status icon
  const getStatusIcon = (status) => {
    switch (status) {
      case 'active':
        return <CheckCircle />;
      case 'ended':
        return <Error />;
      case 'paused':
        return <Warning />;
      default:
        return <Info />;
    }
  };

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Skeleton variant="rectangular" height={400} />
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="error">
          Failed to load experiment: {error.message}
        </Alert>
      </Container>
    );
  }

  if (!experimentData) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="warning">
          Experiment not found
        </Alert>
      </Container>
    );
  }

  const { experiment } = experimentData;

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <IconButton onClick={() => navigate('/experiments')}>
          <ArrowBack />
        </IconButton>
        <Box flexGrow={1}>
          <Typography variant="h4" gutterBottom>
            {experiment.name}
          </Typography>
          <Box display="flex" alignItems="center" gap={2}>
            <Chip
              icon={getStatusIcon(experiment.status)}
              label={experiment.status}
              color={getStatusColor(experiment.status)}
              variant="filled"
            />
            <Typography variant="body2" color="text.secondary">
              Started: {new Date(experiment.start_at).toLocaleString()}
            </Typography>
            {experiment.end_at && (
              <Typography variant="body2" color="text.secondary">
                Ended: {new Date(experiment.end_at).toLocaleString()}
              </Typography>
            )}
            <Typography variant="body2" color="text.secondary">
              Traffic: {experiment.traffic_pct * 100}%
            </Typography>
          </Box>
        </Box>
        <Box display="flex" gap={1}>
          <Tooltip title="Experiment Information">
            <IconButton onClick={() => setInfoDialogOpen(true)}>
              <Info />
            </IconButton>
          </Tooltip>
          <Tooltip title="Refresh Data">
            <IconButton onClick={() => window.location.reload()}>
              <Refresh />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Quick Stats */}
      {summaryData && (
        <Box mb={3}>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <People color="primary" sx={{ fontSize: 40, mb: 1 }} />
                <Typography variant="h6" color="primary">
                  {summaryData.active_users['24h'].toLocaleString()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Active Users (24h)
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Recommend color="primary" sx={{ fontSize: 40, mb: 1 }} />
                <Typography variant="h6" color="primary">
                  {summaryData.serves.total.toLocaleString()}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Total Serves
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <TrendingUp color="primary" sx={{ fontSize: 40, mb: 1 }} />
                <Typography variant="h6" color="primary">
                  {summaryData.rewards.mean_24h.toFixed(3)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Mean Reward (24h)
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Speed color="primary" sx={{ fontSize: 40, mb: 1 }} />
                <Typography variant="h6" color="primary">
                  {summaryData.rewards.current_regret.toFixed(3)}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Current Regret
                </Typography>
              </Paper>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Main Content */}
      <Paper sx={{ mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Overview" icon={<Info />} />
          <Tab label="Reward Trends" icon={<TrendingUp />} />
          <Tab label="Cohort Analysis" icon={<People />} />
          <Tab label="Arm Performance" icon={<Recommend />} />
          <Tab label="Latency" icon={<Speed />} />
          <Tab label="Event Log" icon={<Info />} />
          <Tab label="Guardrails" icon={<Security />} />
        </Tabs>

        <Box sx={{ p: 3 }}>
          {activeTab === 0 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Experiment Overview
              </Typography>
              <SummaryCards experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 1 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Reward Trends
              </Typography>
              <RewardChart experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 2 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Cohort Analysis
              </Typography>
              <CohortBreakdown experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 3 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Arm Performance
              </Typography>
              <ArmPerformance experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 4 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Latency Distribution
              </Typography>
              <LatencyDistribution experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 5 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Event Log
              </Typography>
              <EventLog experimentId={experimentId} />
            </Box>
          )}

          {activeTab === 6 && (
            <Box>
              <Typography variant="h6" gutterBottom>
                Guardrail Status
              </Typography>
              <GuardrailStatus experimentId={experimentId} />
            </Box>
          )}
        </Box>
      </Paper>

      {/* Experiment Information Dialog */}
      <Dialog
        open={infoDialogOpen}
        onClose={() => setInfoDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Experiment Information
        </DialogTitle>
        <DialogContent>
          <List>
            <ListItem>
              <ListItemText
                primary="Experiment ID"
                secondary={experiment.id}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Name"
                secondary={experiment.name}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Status"
                secondary={experiment.status}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Start Date"
                secondary={new Date(experiment.start_at).toLocaleString()}
              />
            </ListItem>
            {experiment.end_at && (
              <ListItem>
                <ListItemText
                  primary="End Date"
                  secondary={new Date(experiment.end_at).toLocaleString()}
                />
              </ListItem>
            )}
            <ListItem>
              <ListItemText
                primary="Traffic Percentage"
                secondary={`${experiment.traffic_pct * 100}%`}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Default Policy"
                secondary={experiment.default_policy}
              />
            </ListItem>
            {experiment.notes && (
              <ListItem>
                <ListItemText
                  primary="Notes"
                  secondary={experiment.notes}
                />
              </ListItem>
            )}
          </List>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setInfoDialogOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ExperimentDashboard;
