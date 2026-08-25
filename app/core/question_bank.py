QUESTION_BANK = [
    # DSA
    {"question": "Explain the difference between a stack and a queue. When would you use each?", "category": "DSA"},
    {"question": "How would you find the second largest element in an unsorted array? What's the optimal time complexity?", "category": "DSA"},
    {"question": "Describe how a hash table works internally. What causes collisions and how are they resolved?", "category": "DSA"},
    {"question": "Given a binary tree, how would you find its maximum depth? Walk through your approach.", "category": "DSA"},
    {"question": "Explain Big-O notation. How would you analyze the time complexity of a nested loop?", "category": "DSA"},
    # System Design
    {"question": "How would you design a URL shortener like bit.ly? Walk through the key components.", "category": "System Design"},
    {"question": "You need to design a real-time chat application for 10 million users. What architecture would you choose?", "category": "System Design"},
    {"question": "Explain the trade-offs between SQL and NoSQL databases. Give a concrete example of when you'd pick each.", "category": "System Design"},
    {"question": "How would you design a notification system that supports email, SMS, and push notifications?", "category": "System Design"},
    {"question": "What is caching? Describe a caching strategy for a high-traffic website.", "category": "System Design"},
    # Behavioral
    {"question": "Tell me about a time you had a conflict with a teammate. How did you resolve it?", "category": "Behavioral"},
    {"question": "Describe a situation where you had to learn a new technology quickly. How did you approach it?", "category": "Behavioral"},
    {"question": "Give an example of when you made a mistake at work. What happened and what did you learn?", "category": "Behavioral"},
    {"question": "How do you prioritize tasks when you have multiple deadlines? Give a specific example.", "category": "Behavioral"},
    {"question": "Tell me about a project you're most proud of. What made it successful?", "category": "Behavioral"},
    # Communication
    {"question": "How would you explain a technical concept to a non-technical stakeholder?", "category": "Communication"},
    {"question": "Describe a time you had to present complex findings to a team. How did you structure your message?", "category": "Communication"},
    {"question": "How do you handle giving feedback to a colleague who is underperforming?", "category": "Communication"},
    {"question": "Explain how you document your code and technical decisions for future team members.", "category": "Communication"},
    {"question": "How do you approach writing emails to senior leadership? Give an example.", "category": "Communication"},
    # Technical Knowledge
    {"question": "What is the difference between REST and GraphQL? When would you choose one over the other?", "category": "Technical Knowledge"},
    {"question": "Explain what CI/CD means and why it matters in software development.", "category": "Technical Knowledge"},
    {"question": "What are design patterns? Name three you've used and explain when each is appropriate.", "category": "Technical Knowledge"},
    {"question": "How does garbage collection work in modern programming languages? Compare at least two approaches.", "category": "Technical Knowledge"},
    {"question": "What is the CAP theorem? Why is it important for distributed systems?", "category": "Technical Knowledge"},
    # Problem Solving
    {"question": "You discover a production system is running 10x slower than usual. Walk through your debugging approach.", "category": "Problem Solving"},
    {"question": "How would you approach refactoring a legacy codebase with no tests?", "category": "Problem Solving"},
    {"question": "A feature request comes in that would require redesigning a core module. How do you evaluate whether to build it?", "category": "Problem Solving"},
    {"question": "Your team's sprint velocity has dropped significantly. What steps would you take to diagnose and fix it?", "category": "Problem Solving"},
    {"question": "How do you decide between building a solution in-house vs. using an existing library or service?", "category": "Problem Solving"},
]

# Backward compatibility: plain question strings
DEFAULT_QUESTIONS = [q["question"] for q in QUESTION_BANK]
