
import dotenv
from src.agents import LLM
from src.refinement import Refiner


def main():
    # Initialize LLM (match how it's done elsewhere in the repo)

    dotenv.load_dotenv()  # Load environment variables from .env file

    llm = LLM()


    # Create Refiner
    refiner = Refiner(llm)

    # Test content (intentionally weak)
    content = """# Assessment: Slides Generation - Chapter 4: Semi-supervised and Reinforcement Learning

## Section 1: Introduction to Semi-supervised Learning

### Learning Objectives
- Understand the motivation behind semi-supervised learning.
- Recognize the significance of semi-supervised learning in machine learning.
- Identify examples of methodologies used in semi-supervised learning.

### Assessment Questions

**Question 1:** What is semi-supervised learning primarily focused on?

  A) Using only labeled data
  B) Combining labeled and unlabeled data
  C) Using no data
  D) Using only unlabeled data

**Correct Answer:** B
**Explanation:** Semi-supervised learning combines labeled and unlabeled data to improve learning accuracy.

**Question 2:** Why is obtaining labeled data often a concern in machine learning?

  A) Labeled data is always abundant
  B) Labeled data is inexpensive to gather
  C) Labeling data can be time-consuming and costly
  D) Labeled data is less informative than unlabeled data

**Correct Answer:** C
**Explanation:** Labeling data requires significant resources, especially in fields like healthcare or specialized fields where expert knowledge is needed.

**Question 3:** What is one of the main advantages of using semi-supervised learning?

  A) It requires more labeled data than supervised learning
  B) It can lead to better model generalization
  C) It replaces the need for any labeled data
  D) It simplifies the model training process completely

**Correct Answer:** B
**Explanation:** Using both labeled and unlabeled data allows models to learn more effectively, enhancing generalization to unseen data.

**Question 4:** Which of the following is a common methodology in semi-supervised learning?

  A) Traditional supervised learning
  B) Clustering without labels
  C) Self-training
  D) Data augmentation only

**Correct Answer:** C
**Explanation:** Self-training is a technique where a model learns from its own predictions on unlabeled data.

### Activities
- Research and present a case study on the application of semi-supervised learning in a specific domain, such as text classification or image analysis.
- Conduct an experiment using a small labeled dataset and a larger unlabeled dataset to train a model and report on the performance improvements observed.

### Discussion Questions
- In what scenarios do you think semi-supervised learning would be more beneficial than purely supervised or unsupervised learning?
- How might advances in data collection methods change the landscape for semi-supervised learning in the future?

---

## Section 2: Key Concepts in Semi-supervised Learning

### Learning Objectives
- Define semi-supervised learning.
- Explain how semi-supervised learning integrates labeled and unlabeled data.
- Identify benefits and common methodologies used in semi-supervised learning.

### Assessment Questions

**Question 1:** What types of data does semi-supervised learning use?

  A) Only labeled data
  B) Only unlabeled data
  C) Both labeled and unlabeled data
  D) None of the above

**Correct Answer:** C
**Explanation:** Semi-supervised learning specifically relies on both labeled and unlabeled data.

**Question 2:** Which of the following is true about labeled data?

  A) It does not help in model training.
  B) It is typically cheap to obtain.
  C) It provides known target outcomes for training.
  D) It is not necessary for semi-supervised learning.

**Correct Answer:** C
**Explanation:** Labeled data provides known target outcomes that are crucial for guiding model training.

**Question 3:** In semi-supervised learning, how does a model typically improve its predictions with unlabeled data?

  A) By ignoring the unlabeled data completely.
  B) By guessing outcomes randomly.
  C) By leveraging similarities to labeled instances.
  D) By solely relying on previous predictions.

**Correct Answer:** C
**Explanation:** The model leverages the patterns derived from labeled instances to infer label information from unlabeled examples.

**Question 4:** Which of the following algorithms is commonly used in semi-supervised learning?

  A) Reinforcement Learning
  B) Self-training
  C) Transfer Learning
  D) Gradient Descent

**Correct Answer:** B
**Explanation:** Self-training is a common algorithm used in semi-supervised learning where the model iteratively labels its own unlabeled data.

### Activities
- Create a flowchart that depicts the training process in semi-supervised learning, highlighting the use of labeled and unlabeled data.

### Discussion Questions
- What are the practical implications of using semi-supervised learning in fields such as healthcare or natural language processing?
- How do you think the availability of unlabeled data might affect the adoption of semi-supervised learning techniques?

---

## Section 3: Benefits of Semi-supervised Learning

### Learning Objectives
- Discuss the advantages of semi-supervised learning.
- Identify scenarios where semi-supervised learning is particularly beneficial.
- Evaluate the implications of using semi-supervised learning in real-world applications.

### Assessment Questions

**Question 1:** Which is a major benefit of semi-supervised learning?

  A) Increased data labeling costs
  B) Better accuracy with less data
  C) Dependency on data quality
  D) Limited applicability

**Correct Answer:** B
**Explanation:** Semi-supervised learning helps achieve better model accuracy with fewer labeled examples.

**Question 2:** Which of the following scenarios is a good fit for semi-supervised learning?

  A) When we have abundant labeled data available
  B) When labeling data is too expensive or time-consuming
  C) When the task involves supervised learning only
  D) When unlabeled data is nonexistent

**Correct Answer:** B
**Explanation:** Semi-supervised learning is particularly beneficial when labeled data is scarce but unlabeled data is plentiful.

**Question 3:** What role do unlabeled data play in semi-supervised learning?

  A) They are ignored completely
  B) They help improve model performance by capturing data distribution
  C) They cause confusion in model training
  D) They replace the need for labeled data

**Correct Answer:** B
**Explanation:** Unlabeled data help enhance model performance by allowing the model to better understand the underlying data distribution.

**Question 4:** Which benefit directly relates to the cost-effectiveness of semi-supervised learning?

  A) More reliance on expert annotators
  B) Reduced need for extensive labeled datasets
  C) Increased complexity in model design
  D) Higher need for computational resources

**Correct Answer:** B
**Explanation:** Semi-supervised learning reduces the need for large labeled datasets, leading to lower labeling costs.

### Activities
- Research and present examples from your field where semi-supervised learning could be applied effectively.
- Create a cost-benefit analysis comparing the traditional supervised learning approach with semi-supervised learning in a specific application.

### Discussion Questions
- In what situations have you encountered the challenges of labeling data, and how could semi-supervised learning help?
- Can you think of any specific domains or applications where semi-supervised learning might not fit well? Why?

---

## Section 4: Common Algorithms

### Learning Objectives
- Identify common algorithms used in semi-supervised learning.
- Explain the functionality of each identified algorithm.
- Differentiate between self-training, co-training, and graph-based methods.

### Assessment Questions

**Question 1:** Which algorithm is NOT commonly associated with semi-supervised learning?

  A) Self-training
  B) Co-training
  C) Reinforcement Learning
  D) Graph-based methods

**Correct Answer:** C
**Explanation:** Reinforcement Learning techniques are distinct from semi-supervised learning algorithms.

**Question 2:** What is the main goal of self-training in semi-supervised learning?

  A) Reduce dimensionality of data
  B) Transfer learning from one domain to another
  C) Label unlabeled data based on a model's predictions
  D) Combining multiple models to improve performance

**Correct Answer:** C
**Explanation:** Self-training is focused on labeling unlabeled data by predicting labels from a trained model.

**Question 3:** In co-training, how many classifiers are used simultaneously?

  A) One
  B) Two
  C) Three
  D) Four

**Correct Answer:** B
**Explanation:** Co-training typically involves two classifiers that learn from different feature sets.

**Question 4:** Which method relies on constructing a graph for label propagation?

  A) Self-training
  B) Co-training
  C) Graph-based methods
  D) K-means clustering

**Correct Answer:** C
**Explanation:** Graph-based methods utilize a graph structure to propagate labels from labeled to unlabeled data points.

### Activities
- Select one semi-supervised learning algorithm (self-training, co-training, or graph-based) and implement a basic version using a dataset of your choice in Python. Document your findings.

### Discussion Questions
- What are the advantages and potential drawbacks of using semi-supervised learning algorithms?
- In what scenarios would you recommend using self-training over co-training, and why?
- How do graph-based methods compare to traditional supervised learning approaches in terms of data utilization?

---

## Section 5: Applications of Semi-supervised Learning

### Learning Objectives
- Recognize real-world applications of semi-supervised learning.
- Understand how semi-supervised learning is implemented in various fields, such as NLP, image classification, and medical diagnosis.

### Assessment Questions

**Question 1:** In which area is semi-supervised learning NOT typically applied?

  A) Natural Language Processing
  B) Image Classification
  C) Financial forecasting
  D) Medical Diagnosis

**Correct Answer:** C
**Explanation:** While semi-supervised learning can be applied in many fields, financial forecasting is less prominent.

**Question 2:** What is a primary advantage of semi-supervised learning over supervised learning?

  A) It requires more labeled data.
  B) It only works with labeled data.
  C) It can utilize unlabeled data to improve model performance.
  D) It eliminates the need for any data.

**Correct Answer:** C
**Explanation:** Semi-supervised learning effectively harnesses both labeled and unlabeled data to enhance performance.

**Question 3:** Which technique is specifically mentioned in relation to image classification in semi-supervised learning?

  A) Deep Learning
  B) Self-training
  C) Reinforcement Learning
  D) Transfer Learning

**Correct Answer:** B
**Explanation:** Self-training is highlighted for its application in improving facial recognition systems through SSL.

**Question 4:** Which application of semi-supervised learning is associated with predicting diseases?

  A) Facial Recognition
  B) Sentiment Analysis
  C) Disease Prediction
  D) Image Segmentation

**Correct Answer:** C
**Explanation:** Disease Prediction in healthcare is a prominent application of semi-supervised learning utilizing patient data.

### Activities
- Research and summarize a real-world application of semi-supervised learning in a field of your choice, detailing the benefits observed.

### Discussion Questions
- What challenges do you think researchers face when applying semi-supervised learning in real-world scenarios?
- How do you think the balance between labeled and unlabeled data affects the performance of semi-supervised learning models?

---

## Section 6: Introduction to Reinforcement Learning

### Learning Objectives
- Understand the foundational concepts of reinforcement learning.
- Identify the roles of agents and environments in reinforcement learning.
- Explain the significance of states, actions, and rewards in the learning process.

### Assessment Questions

**Question 1:** What does an agent do in reinforcement learning?

  A) Collects data
  B) Takes actions to maximize rewards
  C) Studies labeled data
  D) Remains passive

**Correct Answer:** B
**Explanation:** The agent in reinforcement learning takes actions in an environment to maximize cumulative rewards.

**Question 2:** Which component represents the environment in reinforcement learning?

  A) The agent's strategy
  B) The external system the agent interacts with
  C) The rewards given to the agent
  D) The state of the agent

**Correct Answer:** B
**Explanation:** The environment in reinforcement learning is the external system with which the agent interacts.

**Question 3:** What is the main goal of reinforcement learning?

  A) To classify data accurately
  B) To maximize cumulative reward over time
  C) To learn hidden patterns in data
  D) To predict future outcomes based on past data

**Correct Answer:** B
**Explanation:** The primary objective in reinforcement learning is to learn a policy that maximizes cumulative rewards over time.

**Question 4:** How does an agent receive feedback in reinforcement learning?

  A) Through labeled data
  B) Through rewards and penalties from the environment
  C) From pre-defined rules
  D) By observing other agents

**Correct Answer:** B
**Explanation:** An agent in reinforcement learning receives feedback in the form of rewards and penalties based on its actions.

### Activities
- Create a simple simulation to demonstrate agent-environment interaction using a grid-based navigation system where the agent must navigate to a target cell while receiving varying rewards.

### Discussion Questions
- How do you think exploration and exploitation affect the learning process in reinforcement learning?
- Can you think of real-world applications where reinforcement learning could be beneficial? What are they?
- What challenges do you foresee in implementing reinforcement learning algorithms?

---

## Section 7: Core Components of Reinforcement Learning

### Learning Objectives
- Explain each of the core components of reinforcement learning.
- Discuss the significance of the interactions among the components in the reinforcement learning process.
- Analyze how changes in one component can impact others.

### Assessment Questions

**Question 1:** What does the value function represent in reinforcement learning?

  A) The current state of the environment
  B) The agent's strategy for choosing actions
  C) The expected future rewards from a state
  D) The immediate result of an action taken

**Correct Answer:** C
**Explanation:** The value function estimates the expected future rewards from a state under a particular policy, helping the agent evaluate the benefit of being in that state.

**Question 2:** Which component conveys the signal for the success or failure of an action?

  A) State
  B) Action
  C) Reward
  D) Policy

**Correct Answer:** C
**Explanation:** The reward is the scalar value given to the agent after it takes an action in a particular state; it indicates how successful the action was towards achieving a goal.

**Question 3:** What is a policy in the context of reinforcement learning?

  A) A reward function that outputs a scalar value
  B) A mapping from states to actions that defines the agent's behavior
  C) The state of the environment at any point in time
  D) A process by which the agent learns from previous experiences

**Correct Answer:** B
**Explanation:** A policy defines the agent's behavior; it maps states to actions, dictating what action the agent should take in any given state.

**Question 4:** Which of the following represents the interaction of different components during the reinforcement learning process?

  A) Action leads to state change, which results in a reward and updates the policy
  B) State affects the reward which directly updates the value function
  C) Value function determines the state and updates the actions taken
  D) Reward changes the state leading to the selection of actions only

**Correct Answer:** A
**Explanation:** The correct flow is that the action taken influences the state change, resulting in a reward that can then influence the policy adjustment.

### Activities
- Create a visual flowchart that depicts the relationships between state, action, reward, policy, and value function in reinforcement learning.

### Discussion Questions
- How might the understanding of these components change the way you approach training an RL agent?
- Can you think of other real-world scenarios similar to the chess example where reinforcement learning could be applied effectively?

---

## Section 8: Reinforcement Learning Strategies

### Learning Objectives
- Identify and explain key strategies in reinforcement learning, specifically Q-learning and policy gradients.
- Utilize and apply common reinforcement learning strategies to solve basic RL problems effectively.

### Assessment Questions

**Question 1:** What is the primary goal of Q-learning in reinforcement learning?

  A) To learn the value of state-action pairs
  B) To directly optimize policies
  C) To maximize the size of the dataset
  D) To minimize the computation time

**Correct Answer:** A
**Explanation:** Q-learning aims to learn the value of taking actions in particular states to ultimately derive an optimal policy.

**Question 2:** Which of the following variables in the Q-learning update equation represents the learning rate?

  A) r
  B) Q(s, a)
  C) α (alpha)
  D) γ (gamma)

**Correct Answer:** C
**Explanation:** The learning rate, α (alpha), controls how much new information overrides the old in the Q-learning equation.

**Question 3:** In policy gradient methods, what do we optimize directly?

  A) The state values
  B) The action probabilities
  C) The Q-values
  D) The learning rate

**Correct Answer:** B
**Explanation:** Policy gradient methods focus on directly optimizing the action probabilities for given states to improve the policy.

**Question 4:** What is a key advantage of policy gradient methods over value-based methods like Q-learning?

  A) They require less sample data
  B) They handle large state spaces better
  C) They can optimize stochastic policies
  D) They are easier to implement

**Correct Answer:** C
**Explanation:** Policy gradient methods are particularly effective in optimizing stochastic policies or when the action space is continuous.

### Activities
- Implement a basic Q-learning algorithm in Python and simulate its performance navigating a simple grid environment. Visualize how the Q-values are updated over time.
- Create a basic policy gradient agent that learns to solve a simple task (like picking objects) and analyze how actions are adjusted based on reward feedback.

### Discussion Questions
- How might the choice between Q-learning and policy gradients impact performance in different types of environments?
- What are some potential challenges faced when implementing reinforcement learning strategies in real-world applications?

---

## Section 9: Applications of Reinforcement Learning

### Learning Objectives
- Discuss various domains where reinforcement learning can be applied.
- Evaluate real-world examples of reinforcement learning, including specific case studies.

### Assessment Questions

**Question 1:** Which of the following is NOT a common application for reinforcement learning?

  A) Robotics
  B) Game playing
  C) Image classification
  D) Autonomous systems

**Correct Answer:** C
**Explanation:** Image classification is more associated with supervised learning techniques rather than reinforcement learning.

**Question 2:** What is a key challenge in reinforcement learning?

  A) Large amounts of labeled data
  B) Balancing exploration and exploitation
  C) Lack of computational power
  D) Uniform reward signals

**Correct Answer:** B
**Explanation:** Balancing exploration (trying new actions) and exploitation (using known good actions) is crucial in reinforcement learning.

**Question 3:** In which application has reinforcement learning shown significant success, especially recently?

  A) Text translation
  B) Autonomous driving
  C) Image recognition
  D) Data entry automation

**Correct Answer:** B
**Explanation:** Autonomous driving systems utilize reinforcement learning to make real-time decisions and adapt to their environments.

### Activities
- Choose a specific application of reinforcement learning, such as robotics or game playing, and prepare a detailed report on its implementation, discussing the challenges faced and the rewards mechanisms used.

### Discussion Questions
- How do you think the balance between exploration and exploitation impacts the effectiveness of reinforcement learning in different applications?
- What potential ethical considerations arise from the use of reinforcement learning in autonomous systems?

---

## Section 10: Ethical Considerations in Learning Approaches

### Learning Objectives
- Address ethical implications in both semi-supervised and reinforcement learning.
- Understand how bias can affect decision-making in machine learning.
- Recognize the importance of transparency in AI systems.
- Identify socio-economic impacts of AI technology, particularly in job displacement.

### Assessment Questions

**Question 1:** Which of the following is a major ethical consideration in machine learning?

  A) Complexity of algorithms
  B) Data storage size
  C) Bias in decision-making
  D) Speed of processing

**Correct Answer:** C
**Explanation:** Bias in decision-making is a critical ethical consideration, as it can lead to unfair outcomes.

**Question 2:** What can be a consequence of biased training data in semi-supervised learning?

  A) Increased automation capabilities
  B) Inaccurate predictions for under-represented groups
  C) Faster processing speeds
  D) Higher model interpretability

**Correct Answer:** B
**Explanation:** Biased training data can result in models that provide inaccurate predictions for under-represented groups, perpetuating existing biases.

**Question 3:** In reinforcement learning, what ethical concern can arise from misaligned reward systems?

  A) Greater overall accuracy
  B) Deployment of ethical AI practices
  C) Promotion of harmful behaviors
  D) Enhanced user satisfaction

**Correct Answer:** C
**Explanation:** Misaligned reward systems can lead reinforcement learning agents to promote harmful behaviors or outcomes, prioritizing rewards over ethical considerations.

**Question 4:** What is a recommended practice for enhancing the transparency of AI decision-making?

  A) Using more complex algorithms
  B) Reducing data diversity
  C) Developing explainable AI models
  D) Limiting access to model data

**Correct Answer:** C
**Explanation:** Developing explainable AI models helps to enhance the transparency of AI decision-making, making it easier to understand how decisions are made.

### Activities
- Write an essay discussing the ethical implications of bias in machine learning models, including potential strategies for bias detection and correction.
- Create a presentation that outlines an ethical guideline framework for developing semi-supervised and reinforcement learning systems, focusing on reducing bias and enhancing transparency.

### Discussion Questions
- In what ways can we proactively manage bias in training data for machine learning models?
- How can transparency in AI decision-making processes build trust among users?
- What role do organizations have in ensuring fair transitions for workers affected by AI automation?
- Can you think of an example where reinforcement learning might lead to ethical dilemmas? How should it be addressed?

---

."""

    # Test feedback
    feedback = """  {
        "filename": "chapter_4_assessment.md",
        "scores": {
          "alignment": {
            "thought": "The assessment content includes a series of questions directly tied to well-defined learning objectives across multiple sections focused on semi-supervised and reinforcement learning. Each assessment question evaluates the students' understanding of specific concepts outlined in the learning objectives, and the explanations provided after the correct answers reinforce the learning material. However, the overall alignment could be improved by ensuring that all assessment questions activate higher-order thinking skills rather than primarily recall of factual knowledge. Some questions focus more on basic understanding rather than deeper application or analysis, which can affect their alignment with higher academic objectives. Therefore, I rate it as a 3.0 for good alignment with identified learning objectives, but with room for improvement in rigor."
          },
          "clarity": {
            "thought": "The instructions provided for completing assessments in the content are generally clear. However, the organization of materials could use slight improvement for better accessibility, specifically in directing where one should focus for assessments. Each question is clearly stated, with multiple choice formats making it straightforward for students to understand what is expected. Nevertheless, the breadth of material covered and the lack of explicit overall instructions at the beginning could lead to temporary confusion regarding assessment formats. Therefore, while the instructions are solid, they may not be comprehensive enough or prominent enough to warrant a higher score."
          },
          "availability": {
            "thought": "The content provides a comprehensive overview of assessment questions, activities, and discussion points related to semi-supervised and reinforcement learning, but it lacks explicit rubrics or scoring criteria for the learners to understand how their performance will be evaluated. This can lead to confusion among learners about how to gauge their understanding or success in the assessment. While the assessment questions are well-structured and the activities are meaningful, the absence of defined evaluation criteria could hinder learners' ability to engage effectively with the material. Therefore, I rate this aspect as Fair, given the need for clarity in evaluation. "
          },
          "formative_feedback": {
            "thought": "The content includes a variety of assessment questions, activities, and discussion topics aimed at evaluating and providing feedback on students' understanding of semi-supervised and reinforcement learning concepts. While there is a fair amount of formative feedback in the form of discussion questions and activities that encourage exploration and research, the assessment questions predominantly focus on selected responses with correct answers rather than facilitating comprehensive feedback mechanisms. Additionally, while self-directed and peer feedback opportunities are encouraged through activities, there is limited explicit guidance on how to provide or implement this feedback effectively. Overall, while the content does provide some formative feedback opportunities, it lacks depth in promoting continuous improvement and reflection compared to a higher standard. Therefore, it falls into the 'Fair' category."
          },
          "variety": {
            "thought": "The assessment content displays a range of multiple assessment methods, including quiz questions, activities, and discussion prompts, which allows students to demonstrate their understanding of semi-supervised and reinforcement learning principles. However, the assessments primarily consist of traditional question formats (multiple choice), and while there are practical activities, the overall range for assessments could be broader to encompass even more diverse methods such as projects, peer reviews, or presentations. This limits the score as the intended variety is not fully realized. Therefore, I rate it as fair since it does provide some variety but could be improved significantly."
          }
        },
        "average": 2.7
        }"""
    content_type = "assessment"
    constraints = refiner.translate_feedback(feedback)

    # Run refinement
    improved = refiner.refine(content, constraints, content_type)

    # Print results
    print("\n=== ORIGINAL ===")
    print(content)


if __name__ == "__main__":
    main()