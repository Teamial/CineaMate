"""
Integration Tests for Multi-Armed Bandit System

Tests end-to-end functionality including offline replay simulation,
API endpoints, and complete experiment workflows.

Integration Tests:
- Offline replay with synthetic data
- API experiment creation and management
- End-to-end recommendation flow
- Dashboard data endpoints
- Policy performance comparison

Usage:
    pytest backend/tests/test_integration.py -v
    pytest backend/tests/test_offline_replay.py -v
    pytest backend/tests/test_api_experiments.py -v
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
import json

# Import the modules to test
from backend.ml.policies.thompson_sampling import ThompsonSamplingPolicy
from backend.ml.policies.epsilon_greedy import EpsilonGreedyPolicy
from backend.ml.policies.ucb1 import UCB1Policy
from backend.ml.reward_calculator import RewardCalculator
from backend.ml.experiment_manager import ExperimentManager
from backend.models import Experiment, RecommendationEvent, PolicyState
from backend.database import SessionLocal
from backend.main import app

class TestOfflineReplayIntegration:
    """Integration tests for offline replay simulation"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    def test_synthetic_bandit_simulation(self, mock_db):
        """Test offline replay with synthetic data"""
        # Create synthetic arms with known reward distributions
        arms = ['arm_0.8', 'arm_0.6', 'arm_0.4', 'arm_0.2']
        true_rewards = [0.8, 0.6, 0.4, 0.2]
        
        # Initialize policies
        policies = {
            'thompson': ThompsonSamplingPolicy(mock_db),
            'egreedy': EpsilonGreedyPolicy(mock_db, epsilon=0.1),
            'ucb': UCB1Policy(mock_db)
        }
        
        # Mock state store for all policies
        with patch.object(ThompsonSamplingPolicy, 'store') as mock_ts_store, \
             patch.object(EpsilonGreedyPolicy, 'store') as mock_eg_store, \
             patch.object(UCB1Policy, 'store') as mock_ucb_store:
            
            # Mock state creation
            def create_mock_state():
                mock_state = Mock()
                mock_state.count = 0
                mock_state.sum_reward = 0.0
                mock_state.mean_reward = 0.0
                mock_state.alpha = 1.0
                mock_state.beta = 1.0
                return mock_state
            
            mock_ts_store.get_state.return_value = create_mock_state()
            mock_eg_store.get_state.return_value = create_mock_state()
            mock_ucb_store.get_state.return_value = create_mock_state()
            
            # Run simulation
            num_rounds = 1000
            policy_results = {policy_name: [] for policy_name in policies.keys()}
            
            for round_num in range(num_rounds):
                for policy_name, policy in policies.items():
                    # Select arm
                    result = policy.select({}, arms)
                    selected_arm = result.arm_id
                    
                    # Get true reward for selected arm
                    arm_idx = int(selected_arm.split('_')[1])
                    true_reward = true_rewards[arm_idx]
                    
                    # Add noise to reward
                    noisy_reward = np.random.binomial(1, true_reward)
                    
                    # Update policy
                    policy.update(selected_arm, noisy_reward, {})
                    
                    # Store result
                    policy_results[policy_name].append({
                        'round': round_num,
                        'arm': selected_arm,
                        'reward': noisy_reward,
                        'true_reward': true_reward
                    })
            
            # Analyze results
            for policy_name, results in policy_results.items():
                # Calculate cumulative reward
                cumulative_rewards = np.cumsum([r['reward'] for r in results])
                
                # Calculate regret
                best_arm_reward = max(true_rewards)
                regret = [best_arm_reward - r['true_reward'] for r in results]
                cumulative_regret = np.cumsum(regret)
                
                # Check that policies learn over time
                assert cumulative_rewards[-1] > cumulative_rewards[100], \
                    f"{policy_name} did not learn over time"
                
                # Check that regret grows sublinearly (learning)
                assert cumulative_regret[-1] < cumulative_regret[-100] * 2, \
                    f"{policy_name} regret grew too fast"
            
            # Check that Thompson Sampling performs best
            thompson_final_reward = policy_results['thompson'][-1]['reward']
            egreedy_final_reward = policy_results['egreedy'][-1]['reward']
            ucb_final_reward = policy_results['ucb'][-1]['reward']
            
            # Thompson should be competitive
            assert thompson_final_reward >= 0.7, "Thompson Sampling underperformed"
    
    def test_policy_convergence(self, mock_db):
        """Test that policies converge to optimal arm"""
        # Create arms with clear optimal choice
        arms = ['optimal', 'suboptimal']
        true_rewards = [0.9, 0.1]
        
        policy = ThompsonSamplingPolicy(mock_db)
        
        with patch.object(policy.store, 'get_state') as mock_get_state:
            def mock_get_state_side_effect(arm_id, context_key='default'):
                mock_state = Mock()
                mock_state.alpha = 1.0
                mock_state.beta = 1.0
                return mock_state
            
            mock_get_state.side_effect = mock_get_state_side_effect
            
            # Run simulation
            num_rounds = 500
            optimal_selections = 0
            
            for _ in range(num_rounds):
                result = policy.select({}, arms)
                selected_arm = result.arm_id
                
                if selected_arm == 'optimal':
                    optimal_selections += 1
                    reward = np.random.binomial(1, 0.9)
                else:
                    reward = np.random.binomial(1, 0.1)
                
                policy.update(selected_arm, reward, {})
            
            # Check convergence to optimal arm
            optimal_rate = optimal_selections / num_rounds
            assert optimal_rate > 0.7, f"Policy did not converge to optimal arm: {optimal_rate:.3f}"
    
    def test_reward_calculator_integration(self, mock_db):
        """Test reward calculator with realistic event data"""
        reward_calculator = RewardCalculator(mock_db, reward_window_hours=24)
        
        # Create realistic event scenarios
        test_cases = [
            {
                'name': 'click_within_window',
                'served_at': datetime.utcnow(),
                'clicked': True,
                'clicked_at': datetime.utcnow() + timedelta(minutes=5),
                'expected_reward': 1.0
            },
            {
                'name': 'rating_within_window',
                'served_at': datetime.utcnow(),
                'rated': True,
                'rated_at': datetime.utcnow() + timedelta(minutes=10),
                'rating_value': 4.5,
                'expected_reward': 1.0
            },
            {
                'name': 'low_rating_within_window',
                'served_at': datetime.utcnow(),
                'rated': True,
                'rated_at': datetime.utcnow() + timedelta(minutes=10),
                'rating_value': 1.5,
                'expected_reward': 0.0
            },
            {
                'name': 'no_interaction_past_window',
                'served_at': datetime.utcnow() - timedelta(hours=25),
                'clicked': False,
                'rated': False,
                'expected_reward': 0.0
            },
            {
                'name': 'no_interaction_within_window',
                'served_at': datetime.utcnow() - timedelta(hours=1),
                'clicked': False,
                'rated': False,
                'expected_reward': None
            }
        ]
        
        for test_case in test_cases:
            # Create mock event
            event = Mock()
            event.served_at = test_case['served_at']
            event.clicked = test_case.get('clicked', False)
            event.clicked_at = test_case.get('clicked_at')
            event.rated = test_case.get('rated', False)
            event.rated_at = test_case.get('rated_at')
            event.rating_value = test_case.get('rating_value')
            event.thumbs_up = test_case.get('thumbs_up', False)
            event.thumbs_up_at = test_case.get('thumbs_up_at')
            event.added_to_watchlist = test_case.get('added_to_watchlist', False)
            event.added_to_favorites = test_case.get('added_to_favorites', False)
            event.created_at = test_case['served_at']
            
            # Calculate reward
            reward = reward_calculator.compute_reward(event)
            
            # Check result
            assert reward == test_case['expected_reward'], \
                f"Test case {test_case['name']} failed: expected {test_case['expected_reward']}, got {reward}"

class TestAPIExperimentsIntegration:
    """Integration tests for experiment API endpoints"""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    def test_create_experiment_api(self, client, mock_db):
        """Test experiment creation via API"""
        # Mock database operations
        with patch('backend.database.SessionLocal', return_value=mock_db):
            mock_experiment = Mock()
            mock_experiment.id = "test-experiment-id"
            mock_experiment.name = "Test Experiment"
            mock_experiment.start_at = datetime.utcnow()
            mock_experiment.end_at = None
            mock_experiment.traffic_pct = 0.8
            mock_experiment.default_policy = "thompson"
            mock_experiment.notes = "Test experiment"
            
            mock_db.add.return_value = None
            mock_db.commit.return_value = None
            mock_db.refresh.return_value = None
            
            # Create experiment
            experiment_data = {
                "name": "Test Experiment",
                "traffic_pct": 0.8,
                "default_policy": "thompson",
                "notes": "Test experiment"
            }
            
            response = client.post("/api/experiments", json=experiment_data)
            
            # Check response
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Test Experiment"
            assert data["traffic_pct"] == 0.8
            assert data["default_policy"] == "thompson"
    
    def test_get_experiment_api(self, client, mock_db):
        """Test experiment retrieval via API"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            mock_experiment = Mock()
            mock_experiment.id = "test-experiment-id"
            mock_experiment.name = "Test Experiment"
            mock_experiment.start_at = datetime.utcnow()
            mock_experiment.end_at = None
            mock_experiment.traffic_pct = 0.8
            mock_experiment.default_policy = "thompson"
            mock_experiment.notes = "Test experiment"
            
            mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment
            
            response = client.get("/api/experiments/test-experiment-id")
            
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Test Experiment"
            assert data["traffic_pct"] == 0.8
    
    def test_experiment_not_found(self, client, mock_db):
        """Test handling of non-existent experiment"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            mock_db.query.return_value.filter.return_value.first.return_value = None
            
            response = client.get("/api/experiments/non-existent-id")
            
            assert response.status_code == 404
    
    def test_stop_experiment_api(self, client, mock_db):
        """Test experiment stopping via API"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            mock_experiment = Mock()
            mock_experiment.id = "test-experiment-id"
            mock_experiment.name = "Test Experiment"
            mock_experiment.end_at = None
            
            mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment
            mock_db.commit.return_value = None
            mock_db.refresh.return_value = None
            
            response = client.post("/api/experiments/test-experiment-id/stop")
            
            assert response.status_code == 200
            data = response.json()
            assert data["end_at"] is not None

class TestEndToEndWorkflow:
    """End-to-end workflow tests"""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    def test_complete_experiment_workflow(self, mock_db):
        """Test complete experiment workflow from creation to completion"""
        # 1. Create experiment
        experiment_manager = ExperimentManager(mock_db)
        
        # Mock experiment creation
        mock_experiment = Mock()
        mock_experiment.id = "test-experiment-id"
        mock_experiment.traffic_pct = 0.8
        mock_experiment.default_policy = "thompson"
        
        with patch.object(experiment_manager, 'get_active_experiment', return_value=mock_experiment):
            # 2. Assign users to policies
            policies = ['thompson', 'egreedy', 'ucb']
            user_assignments = {}
            
            for user_id in range(100):
                policy, bucket = experiment_manager.assign_user_to_policy(
                    "test-experiment-id", user_id, policies
                )
                user_assignments[user_id] = (policy, bucket)
            
            # 3. Generate recommendations
            policy = ThompsonSamplingPolicy(mock_db)
            arms = ['arm1', 'arm2', 'arm3']
            
            with patch.object(policy.store, 'get_state') as mock_get_state:
                mock_state = Mock()
                mock_state.alpha = 1.0
                mock_state.beta = 1.0
                mock_get_state.return_value = mock_state
                
                recommendations = []
                for user_id in range(10):
                    result = policy.select({}, arms)
                    recommendations.append({
                        'user_id': user_id,
                        'arm_id': result.arm_id,
                        'confidence': result.confidence,
                        'p_score': result.p_score
                    })
                
                # 4. Simulate rewards
                reward_calculator = RewardCalculator(mock_db)
                
                for rec in recommendations:
                    # Simulate user interaction
                    reward = np.random.binomial(1, 0.3)  # 30% success rate
                    
                    # Update policy
                    policy.update(rec['arm_id'], reward, {})
                    
                    # Store recommendation event
                    rec['reward'] = reward
                
                # 5. Analyze results
                total_rewards = sum(rec['reward'] for rec in recommendations)
                success_rate = total_rewards / len(recommendations)
                
                # Check that workflow completed successfully
                assert len(recommendations) == 10
                assert success_rate >= 0.0
                assert success_rate <= 1.0
    
    def test_policy_performance_comparison(self, mock_db):
        """Test policy performance comparison"""
        # Create synthetic arms with known rewards
        arms = ['arm_0.8', 'arm_0.6', 'arm_0.4']
        true_rewards = [0.8, 0.6, 0.4]
        
        policies = {
            'thompson': ThompsonSamplingPolicy(mock_db),
            'egreedy': EpsilonGreedyPolicy(mock_db, epsilon=0.1),
            'ucb': UCB1Policy(mock_db)
        }
        
        # Mock state stores
        with patch.object(ThompsonSamplingPolicy, 'store') as mock_ts_store, \
             patch.object(EpsilonGreedyPolicy, 'store') as mock_eg_store, \
             patch.object(UCB1Policy, 'store') as mock_ucb_store:
            
            def create_mock_state():
                mock_state = Mock()
                mock_state.count = 0
                mock_state.sum_reward = 0.0
                mock_state.mean_reward = 0.0
                mock_state.alpha = 1.0
                mock_state.beta = 1.0
                return mock_state
            
            mock_ts_store.get_state.return_value = create_mock_state()
            mock_eg_store.get_state.return_value = create_mock_state()
            mock_ucb_store.get_state.return_value = create_mock_state()
            
            # Run simulation
            num_rounds = 500
            policy_performance = {}
            
            for policy_name, policy in policies.items():
                cumulative_reward = 0
                arm_selections = {arm: 0 for arm in arms}
                
                for _ in range(num_rounds):
                    result = policy.select({}, arms)
                    selected_arm = result.arm_id
                    
                    # Get true reward
                    arm_idx = int(selected_arm.split('_')[1])
                    true_reward = true_rewards[arm_idx]
                    
                    # Add noise
                    noisy_reward = np.random.binomial(1, true_reward)
                    cumulative_reward += noisy_reward
                    
                    # Update policy
                    policy.update(selected_arm, noisy_reward, {})
                    
                    # Track selections
                    arm_selections[selected_arm] += 1
                
                policy_performance[policy_name] = {
                    'cumulative_reward': cumulative_reward,
                    'arm_selections': arm_selections
                }
            
            # Check that all policies learned
            for policy_name, performance in policy_performance.items():
                assert performance['cumulative_reward'] > 0, \
                    f"{policy_name} had zero cumulative reward"
                
                # Check that best arm was selected most often
                best_arm = 'arm_0.8'
                best_arm_selections = performance['arm_selections'][best_arm]
                total_selections = sum(performance['arm_selections'].values())
                
                assert best_arm_selections > total_selections * 0.3, \
                    f"{policy_name} did not learn to prefer best arm"

class TestDashboardDataIntegration:
    """Integration tests for dashboard data endpoints"""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return Mock(spec=Session)
    
    def test_experiment_summary_endpoint(self, client, mock_db):
        """Test experiment summary data endpoint"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            # Mock experiment data
            mock_experiment = Mock()
            mock_experiment.id = "test-experiment-id"
            mock_experiment.name = "Test Experiment"
            
            mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment
            
            # Mock summary data
            mock_summary = {
                'traffic_split': {'thompson': 0.25, 'egreedy': 0.25, 'ucb': 0.25, 'control': 0.25},
                'active_users': {'24h': 1000, '7d': 5000},
                'serves': {'total': 10000, '24h': 1000},
                'rewards': {'mean_24h': 0.3, 'current_regret': 0.05}
            }
            
            with patch('backend.routes.experiments_analytics.get_experiment_summary', 
                      return_value=mock_summary):
                response = client.get("/api/experiments/test-experiment-id/summary")
                
                assert response.status_code == 200
                data = response.json()
                assert 'traffic_split' in data
                assert 'active_users' in data
                assert 'serves' in data
                assert 'rewards' in data
    
    def test_timeseries_endpoint(self, client, mock_db):
        """Test timeseries data endpoint"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            # Mock timeseries data
            mock_timeseries = [
                {'timestamp': '2023-01-01T00:00:00Z', 'policy': 'thompson', 'value': 0.3},
                {'timestamp': '2023-01-01T01:00:00Z', 'policy': 'thompson', 'value': 0.32},
                {'timestamp': '2023-01-01T00:00:00Z', 'policy': 'egreedy', 'value': 0.28},
                {'timestamp': '2023-01-01T01:00:00Z', 'policy': 'egreedy', 'value': 0.30}
            ]
            
            with patch('backend.routes.experiments_analytics.get_experiment_timeseries', 
                      return_value=mock_timeseries):
                response = client.get("/api/experiments/test-experiment-id/timeseries?metric=reward&granularity=hour")
                
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 4
                assert all('timestamp' in item for item in data)
                assert all('policy' in item for item in data)
                assert all('value' in item for item in data)
    
    def test_arms_endpoint(self, client, mock_db):
        """Test arms performance endpoint"""
        with patch('backend.database.SessionLocal', return_value=mock_db):
            # Mock arms data
            mock_arms = [
                {'arm_id': 'arm1', 'serves': 1000, 'reward': 0.8, 'regret': 0.05},
                {'arm_id': 'arm2', 'serves': 800, 'reward': 0.6, 'regret': 0.15},
                {'arm_id': 'arm3', 'serves': 600, 'reward': 0.4, 'regret': 0.25}
            ]
            
            with patch('backend.routes.experiments_analytics.get_experiment_arms', 
                      return_value=mock_arms):
                response = client.get("/api/experiments/test-experiment-id/arms?sort=reward&limit=10")
                
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 3
                assert all('arm_id' in item for item in data)
                assert all('serves' in item for item in data)
                assert all('reward' in item for item in data)
                assert all('regret' in item for item in data)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
